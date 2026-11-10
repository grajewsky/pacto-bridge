package pl.pactobridge.pacto_bridge

import java.io.DataInputStream
import java.io.InputStream
import java.nio.ByteBuffer
import java.util.UUID

/** Independent WFTNP wire implementation; protocol references in NETWORK_PROTOCOL.md. */
internal data class DirconMessage(val type: Int, val sequence: Int, val status: Int, val body: ByteArray) {
    fun bytes(): ByteArray {
        require(body.size <= 4096)
        return byteArrayOf(1,type.toByte(),sequence.toByte(),status.toByte(),
            (body.size shr 8).toByte(),body.size.toByte()) + body
    }
    companion object {
        fun read(input: InputStream): DirconMessage? {
            val first=input.read()
            if (first<0) return null
            require(first==1) { "Unsupported WFTNP version" }
            val stream=DataInputStream(input)
            val type=stream.readUnsignedByte(); val seq=stream.readUnsignedByte()
            val status=stream.readUnsignedByte(); val size=stream.readUnsignedShort()
            require(size<=4096) { "Oversized WFTNP request" }
            val body=ByteArray(size); stream.readFully(body)
            return DirconMessage(type,seq,status,body)
        }
    }
}

internal fun dirconUuid(short: String): ByteArray {
    val id=UUID.fromString("0000$short-0000-1000-8000-00805f9b34fb")
    return ByteBuffer.allocate(16).putLong(id.mostSignificantBits).putLong(id.leastSignificantBits).array()
}

internal data class DirconReply(val message: DirconMessage, val subscription: Boolean?=null)

/** Read-only running sensor. Network writes never reach Pacto or a motor API. */
internal class DirconProtocol(serial: String) {
    private data class Attribute(val id: ByteArray,val properties: Int,val value: ByteArray?)
    private val services=listOf(dirconUuid("1814"),dirconUuid("180a"))
    private val attributes=listOf(
        listOf(Attribute(dirconUuid("2a53"),4,null),Attribute(dirconUuid("2a54"),1,byteArrayOf(0,0))),
        listOf(Attribute(dirconUuid("2a29"),1,"PactoBridge".toByteArray(Charsets.UTF_8)),
            Attribute(dirconUuid("2a24"),1,"Pacto S22+ WiFi".toByteArray(Charsets.UTF_8)),
            Attribute(dirconUuid("2a25"),1,serial.toByteArray(Charsets.US_ASCII)))
    )
    fun answer(request: DirconMessage): DirconReply {
        fun reply(status: Int,body: ByteArray=byteArrayOf(),subscription: Boolean?=null)=
            DirconReply(DirconMessage(request.type,request.sequence,status,body),subscription)
        if (request.status!=0) return reply(2)
        if (request.type==1) return if(request.body.isEmpty()) reply(0,services.fold(byteArrayOf()) { a,b->a+b }) else reply(2)
        if (request.type==2) {
            if(request.body.size!=16) return reply(2)
            val index=services.indexOfFirst { it.contentEquals(request.body) }
            if(index<0) return reply(3,request.body)
            return reply(0,request.body+attributes[index].fold(byteArrayOf()) { a,b->a+b.id+byteArrayOf(b.properties.toByte()) })
        }
        if(request.type !in 3..5) return reply(1)
        if(request.body.size<16) return reply(2)
        val id=request.body.copyOfRange(0,16)
        val attribute=attributes.flatten().firstOrNull { it.id.contentEquals(id) } ?: return reply(4,id)
        return when(request.type) {
            3 -> if(request.body.size!=16) reply(2,id) else if((attribute.properties and 1)==0) reply(5,id)
                else reply(0,id+attribute.value!!)
            4 -> reply(5,id)
            else -> if(request.body.size!=17 || request.body[16].toInt() !in 0..1) reply(2,id)
                else if((attribute.properties and 4)==0) reply(5,id)
                else reply(0,id,request.body[16].toInt()==1)
        }
    }
    companion object {
        fun notification(packet: ByteArray)=DirconMessage(6,0,0,dirconUuid("2a53")+packet).bytes()
    }
}
