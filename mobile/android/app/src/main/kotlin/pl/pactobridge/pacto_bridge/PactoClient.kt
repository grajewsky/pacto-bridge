@file:Suppress("DEPRECATION", "OVERRIDE_DEPRECATION", "MissingPermission")
package pl.pactobridge.pacto_bridge

import android.bluetooth.*
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock

/** Operator-led stopped-belt validation path; no general live override. */
internal class PactoClient(private val context: Context, private val publisher: LivePublisher,
    private val emit: (Map<String, Any?>) -> Unit) {
    private val manager = context.getSystemService(BluetoothManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private var client: BluetoothGatt? = null
    private var notify: BluetoothGattCharacteristic? = null
    private var write: BluetoothGattCharacteristic? = null
    private var session: PactoSession? = null
    private var journal: SessionJournal? = null
    private val frames = PactoWireFrames()
    private var writePending = false
    private var epoch = 0
    private var metadataIndex = -1
    private val metadataIds = listOf(uuid("2a26"),uuid("2a27"))
    private val metadataValues = listOf("05","C0.00.C0.00")

    private fun report(row: Map<String, Any?>) { journal?.write(row); emit(row) }
    private fun state(state: String, text: String) = report(mapOf("kind" to "session_state", "state" to state,"message" to text))

    fun connect(address: String, stopped: Boolean, operatorPresent: Boolean, preserveTransport: Boolean=false) {
        LiveSessionPolicy.requireStoppedOperatorSession(stopped,operatorPresent)
        check(BluetoothAdapter.checkBluetoothAddress(address)) { "Nieprawidłowy adres BLE" }
        check(manager.adapter?.isEnabled == true) { "Włącz Bluetooth." }
        stop(preservePublisher=preserveTransport)
        journal = SessionJournal(context)
        report(mapOf("kind" to "session", "address" to address,"stopped_confirmed" to true,
            "operator_present" to true,"file" to journal!!.file.absolutePath))
        state("CONNECTING","Łączenie na postoju; nie naciskaj jeszcze START.")
        val token = epoch
        client = manager.adapter.getRemoteDevice(address).connectGatt(context,false,callback,BluetoothDevice.TRANSPORT_LE)
        if (client == null) { abort("Android nie utworzył klienta GATT."); return }
        handler.postDelayed({ if (token==epoch && session==null) abort("Przekroczony czas przygotowania BLE.") },20000)
    }

    private fun abort(message: String) {
        report(mapOf("kind" to "error","message" to message))
        val waiting=publisher.canWaitForSource()
        stop("Sesja zamknięta: $message Użyj fizycznego STOP, jeśli pas jedzie.", preservePublisher=waiting)
        if (waiting) emit(mapOf("kind" to "status", "message" to
            "Zwift pozostaje połączony bez pomiarów. Wybudź panel fizycznym STOP i przygotuj nową sesję Pacto."))
    }

    private val callback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt,status: Int,newState: Int) { handler.post {
            if (client !== g) { g.close(); return@post }
            report(mapOf("kind" to "gatt_state","status" to status,"state" to newState))
            if (status==BluetoothGatt.GATT_SUCCESS && newState==BluetoothProfile.STATE_CONNECTED) {
                state("DISCOVERING","Połączono. Odkrywanie rzeczywistych charakterystyk BLE.")
                if (!g.discoverServices()) abort("Nie rozpoczęto odkrywania usług.")
            } else if (status!=BluetoothGatt.GATT_SUCCESS || newState==BluetoothProfile.STATE_DISCONNECTED) {
                stop("Bieżnia rozłączona; dane i gotowość unieważnione. Brak automatycznego ponownego START.")
            }
        } }
        override fun onServicesDiscovered(g: BluetoothGatt,status: Int) { handler.post {
            if (client !== g) return@post
            if (status!=BluetoothGatt.GATT_SUCCESS) { abort("Błąd odkrywania GATT: $status"); return@post }
            val services=g.services.filter { it.uuid==uuid("fff0") }
            if (services.size!=1) { abort("Nie znaleziono jednoznacznej usługi FFF0."); return@post }
            val chars=services.single().characteristics
            val candidates=chars.filter { it.uuid in listOf(uuid("fff1"),uuid("fff2")) }
            val ns=candidates.filter { (it.properties and BluetoothGattCharacteristic.PROPERTY_NOTIFY)!=0 }
            val ws=candidates.filter { (it.properties and BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE)!=0 }
            if (ns.size!=1 || ws.size!=1 || ns.single().uuid!=uuid("fff1") || ws.single().uuid!=uuid("fff2")) {
                abort("Układ GATT nie odpowiada udokumentowanemu Pacto."); return@post
            }
            notify=ns.single(); write=ws.single()
            report(mapOf("kind" to "layout","notify" to notify!!.uuid.toString(),"write" to write!!.uuid.toString(),
                "notify_properties" to notify!!.properties,"write_properties" to write!!.properties))
            val d=notify!!.getDescriptor(uuid("2902"))
            if (d==null || !g.setCharacteristicNotification(notify,true)) { abort("Brak subskrypcji FFF1."); return@post }
            d.value=BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            if (!g.writeDescriptor(d)) abort("Android odrzucił zapis CCCD.")
        } }
        override fun onDescriptorWrite(g: BluetoothGatt,d: BluetoothGattDescriptor,status: Int) { handler.post {
            if (client !== g) return@post
            if (d.uuid!=uuid("2902") || d.characteristic.uuid!=notify?.uuid || status!=BluetoothGatt.GATT_SUCCESS) {
                abort("Niepotwierdzona subskrypcja FFF1."); return@post
            }
            state("IDENTIFYING","Powiadomienia włączone. Sprawdzanie wersji i identyfikacji Pacto.")
            val token=epoch
            handler.postDelayed({ if (token==epoch && client===g) { metadataIndex=0; readMetadata(g) } },1000)
        } }
        override fun onCharacteristicRead(g: BluetoothGatt,c: BluetoothGattCharacteristic,status: Int) {
            metadata(g,c,c.value?.clone() ?: byteArrayOf(),status)
        }
        override fun onCharacteristicRead(g: BluetoothGatt,c: BluetoothGattCharacteristic,value: ByteArray,status: Int) {
            metadata(g,c,value.clone(),status)
        }
        override fun onCharacteristicWrite(g: BluetoothGatt,c: BluetoothGattCharacteristic,status: Int) { handler.post {
            if (client!==g || c.uuid!=write?.uuid || !writePending) return@post
            writePending=false
            report(mapOf("kind" to "write_result","status" to status))
            session?.writeFinished(status==BluetoothGatt.GATT_SUCCESS)
        } }
        override fun onCharacteristicChanged(g: BluetoothGatt,c: BluetoothGattCharacteristic) {
            incoming(g,c,c.value?.clone() ?: return)
        }
        override fun onCharacteristicChanged(g: BluetoothGatt,c: BluetoothGattCharacteristic,value: ByteArray) {
            incoming(g,c,value.clone())
        }
    }

    private fun metadata(g: BluetoothGatt,c: BluetoothGattCharacteristic,value: ByteArray,status: Int) { handler.post {
        if (client!==g || metadataIndex !in 0..1 || c.uuid!=metadataIds[metadataIndex]) return@post
        val text=value.toString(Charsets.US_ASCII)
        report(mapOf("kind" to "device_info","uuid" to c.uuid.toString(),"value" to text,"status" to status))
        if (status!=BluetoothGatt.GATT_SUCCESS || text!=metadataValues[metadataIndex]) {
            abort("Wersja urządzenia nie odpowiada zapisanej sesji Pacto."); return@post
        }
        metadataIndex++
        if (metadataIndex==2) beginSession(g) else readMetadata(g)
    } }

    private fun readMetadata(g: BluetoothGatt) {
        val c=g.getService(uuid("180a"))?.getCharacteristic(metadataIds[metadataIndex])
        if (c==null || (c.properties and BluetoothGattCharacteristic.PROPERTY_READ)==0 || !g.readCharacteristic(c)) {
            abort("Brak czytelnych pól wersji 2A26/2A27."); return
        }
        val index=metadataIndex; val token=epoch
        handler.postDelayed({ if (token==epoch && metadataIndex==index) abort("Brak odpowiedzi wersji urządzenia.") },3000)
    }

    private fun beginSession(g: BluetoothGatt) {
        if (client!==g || session!=null) return
        val s=PactoSession({ SystemClock.elapsedRealtime() }, { data -> send(g,data) },
            { value,text ->
                state(value,text)
                if (value == "STALE" && client === g) {
                    publisher.onTelemetryStale()
                }
                if (value == "READY" && client === g) {
                    val accepted = g.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_BALANCED)
                    report(mapOf("kind" to "transport", "request" to "balanced_connection_priority", "accepted" to accepted))
                }
            },
            { tenths ->
                report(mapOf("kind" to "speed","kmh" to tenths/10.0,"source" to "live Pacto B2"))
                publisher.onLiveMeasurement(tenths)
            }, { text -> abort(text) }, { stop("Fizyczny STOP potwierdzony telemetrią zero. Most rozłączony.") })
        session=s
        s.begin()
        handler.post(tick)
    }

    private val tick=object : Runnable {
        override fun run() {
            session?.tick()
            if (session!=null) handler.postDelayed(this,100)
        }
    }

    private fun send(g: BluetoothGatt,data: ByteArray) {
        val c=write
        if (client!==g || c==null || writePending) { abort("Niespójna kolejka zapisów GATT."); return }
        writePending=true
        report(mapOf("kind" to "write","hex" to data.pactoHex()))
        c.writeType=BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
        c.value=data.clone()
        try {
            if (!g.writeCharacteristic(c)) { writePending=false; session?.writeFinished(false) }
        } catch (e: Exception) { abort("Błąd zapisu GATT: ${e.message}") }
    }

    private fun incoming(g: BluetoothGatt,c: BluetoothGattCharacteristic,data: ByteArray) { handler.post {
        if (client!==g || c.uuid!=notify?.uuid || c.service?.uuid!=uuid("fff0")) return@post
        report(mapOf("kind" to "notification","hex" to data.pactoHex()))
        frames.feed(data).forEach { session?.frame(it) }
    } }

    fun stop(message: String="Most rozłączony. To nie jest komenda STOP bieżni.", preservePublisher: Boolean=false) {
        epoch++
        handler.removeCallbacks(tick)
        val g=client; client=null; session=null; writePending=false; metadataIndex=-1
        notify=null; write=null; frames.reset()
        if (!preservePublisher) publisher.stop()
        try { g?.disconnect(); g?.close() } catch (_: Exception) { }
        report(mapOf("kind" to "unavailable"))
        state("INACTIVE",message)
        journal=null
    }
}
