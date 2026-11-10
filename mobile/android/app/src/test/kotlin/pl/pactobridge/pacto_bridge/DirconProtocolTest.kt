package pl.pactobridge.pacto_bridge

import java.io.ByteArrayInputStream
import java.io.EOFException
import org.junit.Assert.*
import org.junit.Test

class DirconProtocolTest {
    private val profile=DirconProtocol("PB22-test")
    private fun request(type: Int,body: ByteArray=byteArrayOf())=profile.answer(DirconMessage(type,231,0,body))
    @Test fun fragmentedAndConsecutiveTcpFramesPreserveSequenceAndPayload() {
        val one=DirconMessage(2,255,0,dirconUuid("1814"))
        val input=object: ByteArrayInputStream(one.bytes()+DirconMessage(1,4,0,byteArrayOf()).bytes()) {
            override fun read(b: ByteArray,off: Int,len: Int)=super.read(b,off,minOf(2,len))
        }
        val decoded=DirconMessage.read(input)!!
        assertEquals(255,decoded.sequence); assertArrayEquals(one.body,decoded.body)
        assertEquals(1,DirconMessage.read(input)!!.type); assertNull(DirconMessage.read(input))
    }
    @Test fun serviceDiscoveryUsesNetworkOrder128BitUuids() {
        val response=request(1).message
        assertEquals(231,response.sequence); assertEquals(0,response.status)
        assertEquals(32,response.body.size)
        assertArrayEquals(pactoHex("00 00 18 14 00 00 10 00 80 00 00 80 5f 9b 34 fb"),response.body.take(16).toByteArray())
    }
    @Test fun measurementOnlyNotifiesAndFeatureIsReadOnly() {
        val response=request(2,dirconUuid("1814")).message
        assertEquals(50,response.body.size)
        assertEquals(4,response.body[32].toInt()); assertEquals(1,response.body[49].toInt())
        val feature=request(3,dirconUuid("2a54")).message
        assertEquals(0,feature.status); assertArrayEquals(byteArrayOf(0,0),feature.body.drop(16).toByteArray())
        assertEquals(5,request(3,dirconUuid("2a53")).message.status)
    }
    @Test fun notificationsAreOptInAndDoNotSupplyASample() {
        val enabled=request(5,dirconUuid("2a53")+byteArrayOf(1))
        assertEquals(true,enabled.subscription); assertEquals(16,enabled.message.body.size)
        assertEquals(false,request(5,dirconUuid("2a53")+byteArrayOf(0)).subscription)
        assertNull(request(5,dirconUuid("2a54")+byteArrayOf(1)).subscription)
        assertEquals(2,request(5,dirconUuid("2a53")+byteArrayOf(2)).message.status)
    }
    @Test fun writesCannotOperateMotorOrChangeSource() {
        assertEquals(5,request(4,dirconUuid("2a53")+pactoHex("f0 a5 01 d3 02 6b")).message.status)
        assertEquals(4,request(4,dirconUuid("2ad9")+byteArrayOf(7)).message.status)
    }
    @Test fun unknownServiceCharacteristicAndMessageHaveExplicitErrors() {
        assertEquals(3,request(2,dirconUuid("1826")).message.status)
        assertEquals(4,request(3,dirconUuid("ffff")).message.status)
        assertEquals(1,request(99).message.status)
        assertEquals(2,request(2,byteArrayOf(1)).message.status)
    }
    @Test fun notificationEncapsulatesActualRscUnitsWithoutRewritingSpeed() {
        val packet=rscPacket(20)
        val message=DirconMessage.read(ByteArrayInputStream(DirconProtocol.notification(packet)))!!
        assertEquals(6,message.type); assertEquals(20,message.body.size)
        assertArrayEquals(pactoHex("00 8e 00 00"),message.body.drop(16).toByteArray())
    }
    @Test(expected=IllegalArgumentException::class)
    fun oversizedFrameIsRejectedBeforeAllocation() {
        DirconMessage.read(ByteArrayInputStream(byteArrayOf(1,1,0,0,0x10,1)))
    }
    @Test(expected=EOFException::class)
    fun truncatedPayloadDoesNotBecomeARequest() {
        DirconMessage.read(ByteArrayInputStream(byteArrayOf(1,2,0,0,0,16,1)))
    }
}
