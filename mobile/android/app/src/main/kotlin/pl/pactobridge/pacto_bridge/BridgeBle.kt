@file:Suppress("DEPRECATION", "MissingPermission")
package pl.pactobridge.pacto_bridge

import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import java.util.UUID

internal class BridgeBle(private val context: Context, private val emit: (Map<String, Any?>) -> Unit) {
    private val manager = context.getSystemService(BluetoothManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private val blePublisher = RscPublisher(context, emit)
    private val wifiPublisher = DirconPublisher(context, emit)
    private var selectedPublisher: LivePublisher = wifiPublisher
    private val publisher = object : LivePublisher {
        override fun requireReceiver() = selectedPublisher.requireReceiver()
        override fun canWaitForSource() = selectedPublisher.canWaitForSource()
        override fun onLiveMeasurement(tenthsKmh: Int) = selectedPublisher.onLiveMeasurement(tenthsKmh)
        override fun stop() { blePublisher.stop(); wifiPublisher.stop() }
    }
    private val radioProbe = RadioProbe(context, emit)
    private val liveClient = PactoClient(context, publisher, emit)
    private val seenDevices = HashMap<String, Long>()
    private var scanning = false
    private var generation = 0

    fun capabilities(): Map<String, Any?> {
        val a = manager.adapter
        val map = mapOf("model" to "${Build.MANUFACTURER} ${Build.MODEL} • Android ${Build.VERSION.RELEASE}",
            "enabled" to (a?.isEnabled == true),
            "central" to context.packageManager.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE),
            "peripheral" to (a?.isEnabled == true && a.isMultipleAdvertisementSupported && a.bluetoothLeAdvertiser != null),
            "liveVerified" to false)
        emit(mapOf("kind" to "status", "message" to "Diagnostyka telefonu zakończona. Nadawanie live nie zostało uruchomione."))
        return map
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(type: Int, result: ScanResult) {
            val name = result.scanRecord?.deviceName ?: result.device.name
            if (name != "iConsole+0106") return
            seenDevices[result.device.address] = SystemClock.elapsedRealtime()
            emit(mapOf("kind" to "device", "name" to name,
                "address" to result.device.address, "rssi" to result.rssi))
        }
        override fun onScanFailed(code: Int) {
            scanning = false
            emit(mapOf("kind" to "error", "message" to "Błąd skanowania BLE: $code"))
        }
    }

    fun scan() {
        check(manager.adapter?.isEnabled == true) { "Włącz Bluetooth w telefonie." }
        stopScan()
        val token = generation
        scanning = true
        manager.adapter.bluetoothLeScanner.startScan(null,
            ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), scanCallback)
        emit(mapOf("kind" to "status", "message" to "Skanowanie przez 12 sekund; bez łączenia z bieżnią."))
        handler.postDelayed({ if (token == generation) {
            stopScan(); emit(mapOf("kind" to "status", "message" to "Skanowanie zakończone."))
        } }, 12000)
    }

    private fun stopScan() {
        if (scanning) {
            try { manager.adapter?.bluetoothLeScanner?.stopScan(scanCallback) } catch (_: SecurityException) { }
            scanning = false
        }
        generation++
    }

    fun probeGatt() = blePublisher.probe()
    // Deliberately does not close a live client: diagnostic coexistence test.
    fun probeRadio() { radioProbe.start() }
    fun prepareReceiver(transport: String) {
        require(transport in listOf("wifi","ble")) { "Nieznany transport" }
        stop()
        selectedPublisher=if(transport=="wifi") wifiPublisher else blePublisher
        if(transport=="wifi") wifiPublisher.prepareReceiver() else blePublisher.prepareReceiver()
    }
    fun connectSession(address: String, stopped: Boolean, operatorPresent: Boolean) {
        LiveSessionPolicy.requireStoppedOperatorSession(stopped,operatorPresent)
        check(seenDevices[address]?.let { SystemClock.elapsedRealtime()-it<60000 } == true) {
            "Najpierw wykonaj świeże skanowanie i wybierz iConsole+0106."
        }
        publisher.requireReceiver()
        stopScan(); radioProbe.stop()
        liveClient.connect(address,stopped,operatorPresent,preserveTransport=true)
    }
    // Legacy unrestricted entry point remains blocked. Only the stopped-operator
    // session workflow above can establish a connection.
    fun connect(@Suppress("UNUSED_PARAMETER") address: String) = LiveSessionPolicy.requireVerified()

    fun stop() {
        stopScan()
        liveClient.stop()
        publisher.stop(); radioProbe.stop()
        emit(mapOf("kind" to "unavailable"))
    }
}

internal fun uuid(short: String): UUID = UUID.fromString("0000$short-0000-1000-8000-00805f9b34fb")
