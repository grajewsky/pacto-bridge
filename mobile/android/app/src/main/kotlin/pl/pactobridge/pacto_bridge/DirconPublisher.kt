package pl.pactobridge.pacto_bridge

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import java.net.ServerSocket
import java.net.Socket
import java.net.InetSocketAddress
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/** Local-network RSC only; no packet from the network can operate the treadmill. */
internal class DirconPublisher(context: Context,private val emit: (Map<String,Any?>)->Unit) : LivePublisher {
    private val nsd=context.getSystemService(NsdManager::class.java)
    private val handler=Handler(Looper.getMainLooper())
    private val source=NetworkSampleGate { SystemClock.elapsedRealtime() }
    private val peers=ConcurrentHashMap<String,Peer>()
    private var socket: ServerSocket?=null
    private var registration: NsdManager.RegistrationListener?=null
    private var latest: ByteArray?=null
    private var publishing=false
    private var reportedAgeSeconds=-1L
    @Volatile private var epoch=0
    private val identity: String
    private val protocol: DirconProtocol
    init {
        val preferences=context.getSharedPreferences("network_sensor",Context.MODE_PRIVATE)
        identity=preferences.getString("identity",null) ?: UUID.randomUUID().toString().replace("-","")
            .take(6).also { preferences.edit().putString("identity",it).apply() }
        protocol=DirconProtocol("PB22-$identity")
    }
    private fun message(text: String)=emit(mapOf("kind" to "status","message" to text))
    override fun canWaitForSource()=source.waitingForSource()
    override fun requireReceiver() {
        check(source.active && socket?.isClosed==false) { "Najpierw włącz tryb WiFi." }
    }
    fun prepareReceiver() {
        stop(); source.prepare()
        val listener=ServerSocket().apply { reuseAddress=true; bind(InetSocketAddress(36866),4) }
        socket=listener
        val token=epoch
        val info=NsdServiceInfo().apply {
            serviceName="PactoBridge WiFi $identity"
            serviceType="_wahoo-fitness-tnp._tcp."
            port=listener.localPort
            setAttribute("serial-number","PB22-$identity")
            setAttribute("mac-address","02:50:42:"+identity.chunked(2).joinToString(":"))
            setAttribute("ble-service-uuids","00001814-0000-1000-8000-00805f9b34fb")
        }
        val callback=object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(registered: NsdServiceInfo) { handler.post {
                if(token!=epoch) { try { nsd.unregisterService(this) } catch (_: Exception) { }; return@post }
                emit(mapOf("kind" to "transport_state","state" to "WIFI_READY",
                    "message" to "WiFi aktywne: ${registered.serviceName}. Przygotuj Pacto na postoju, potem wybierz czujnik w Zwift BIEG (ikona WiFi).",
                    "network_name" to registered.serviceName,"port" to listener.localPort))
            } }
            override fun onRegistrationFailed(service: NsdServiceInfo,error: Int) { handler.post {
                if(token==epoch) { stop(); message("Nie zarejestrowano czujnika WiFi: $error") }
            } }
            override fun onServiceUnregistered(service: NsdServiceInfo) { }
            override fun onUnregistrationFailed(service: NsdServiceInfo,error: Int) { }
        }
        registration=callback
        try { nsd.registerService(info,NsdManager.PROTOCOL_DNS_SD,callback) }
        catch(e: Exception) { stop(); throw e }
        Thread({
            try {
                while(!listener.isClosed && token==epoch) {
                    val connection=listener.accept()
                    if(peers.size>=4 || token!=epoch) { connection.close(); continue }
                    connection.tcpNoDelay=true; connection.keepAlive=true
                    val peer=Peer(connection,token); peers[peer.id]=peer
                    Thread({ peer.readRequests() },"Pacto-WFTNP-read").apply { isDaemon=true; start() }
                }
            } catch (_: Exception) {
                handler.post { if(token==epoch) { stop(); message("Serwer WiFi zakończył połączenie.") } }
            }
        },"Pacto-WFTNP-accept").apply { isDaemon=true; start() }
    }

    private data class Delivery(val packet: ByteArray,val timestamp: Long)
    private inner class Peer(val connection: Socket,val token: Int) {
        val id=UUID.randomUUID().toString()
        @Volatile var subscribed=false
        private val output=connection.getOutputStream()
        private val writer=Executors.newSingleThreadExecutor { task->Thread(task,"Pacto-WFTNP-write").apply { isDaemon=true } }
        private val queued=AtomicReference<Delivery?>(null)
        private val writing=AtomicBoolean(false)
        @Synchronized private fun send(bytes: ByteArray) { output.write(bytes); output.flush() }
        fun publish(packet: ByteArray) {
            queued.set(Delivery(packet,SystemClock.elapsedRealtime()))
            if(!writing.compareAndSet(false,true)) return
            try { writer.execute {
                try {
                    while(true) {
                        val delivery=queued.getAndSet(null) ?: break
                        if(token==epoch && subscribed && SystemClock.elapsedRealtime()-delivery.timestamp<3000)
                            send(DirconProtocol.notification(delivery.packet))
                    }
                } catch (_: Exception) { close() }
                finally {
                    writing.set(false)
                    val remaining=queued.getAndSet(null)
                    if(remaining!=null && token==epoch && subscribed &&
                        SystemClock.elapsedRealtime()-remaining.timestamp<3000) publish(remaining.packet)
                }
            } } catch (_: Exception) { writing.set(false); close() }
        }
        fun readRequests() {
            try {
                val input=connection.getInputStream()
                while(token==epoch && !connection.isClosed) {
                    val request=DirconMessage.read(input) ?: break
                    val answer=protocol.answer(request)
                    send(answer.message.bytes())
                    answer.subscription?.let { enabled->
                        subscribed=enabled
                        handler.post {
                            if(token==epoch && enabled) {
                                emit(mapOf("kind" to "transport_state","state" to "RECEIVER_READY",
                                    "message" to "Odbiornik WiFi połączony. Przygotuj teraz Pacto na postoju."))
                            }
                        }
                    }
                }
            } catch (_: Exception) { }
            finally {
                close(); peers.remove(id)
                handler.post { if(token==epoch && peers.values.none { it.subscribed }) {
                    emit(mapOf("kind" to "transport_state","state" to "WIFI_READY",
                        "message" to "Odbiornik WiFi rozłączony. Czujnik pozostaje dostępny; przygotuj Pacto i połącz Zwift."))
                } }
            }
        }
        fun close() {
            subscribed=false; queued.set(null)
            try { connection.close() } catch (_: Exception) { }
            writer.shutdownNow()
        }
    }

    override fun onLiveMeasurement(tenthsKmh: Int) {
        val bytes=try { rscPacket(tenthsKmh) } catch (_: IllegalArgumentException) { stop(); return }
        try { source.sample() } catch (_: IllegalStateException) { stop(); return }
        latest=bytes
        if (!publishing) { publishing=true; handler.post(tick) }
    }
    // A missed BLE read never cancels the independent network sender.
    override fun onTelemetryStale() {}
    private val tick=object : Runnable {
        override fun run() {
            if(!source.canPublish()) { publishing=false; return }
            latest?.let { packet->peers.values.filter { it.subscribed }.forEach { it.publish(packet) } }
            val age=source.ageMs() ?: 0L
            if(age/1000!=reportedAgeSeconds) {
                reportedAgeSeconds=age/1000
                emit(mapOf("kind" to "sample_age", "age_ms" to age))
            }
            handler.postDelayed(this,250)
        }
    }
    override fun stop() {
        publishing=false; reportedAgeSeconds=-1
        epoch++; handler.removeCallbacks(tick)
        registration?.let { try { nsd.unregisterService(it) } catch (_: Exception) { } }; registration=null
        try { socket?.close() } catch (_: Exception) { }; socket=null
        peers.values.forEach { it.close() }; peers.clear(); latest=null; source.reset()
        emit(mapOf("kind" to "transport_state","state" to "INACTIVE"))
    }
}
