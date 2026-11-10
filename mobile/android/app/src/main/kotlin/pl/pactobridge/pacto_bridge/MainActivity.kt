package pl.pactobridge.pacto_bridge

import android.Manifest
import android.content.pm.PackageManager
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private lateinit var ble: BridgeBle
    private var sink: EventChannel.EventSink? = null
    private var pending: MethodChannel.Result? = null
    private val permissions = arrayOf(Manifest.permission.BLUETOOTH_SCAN,
        Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_ADVERTISE)

    override fun configureFlutterEngine(engine: FlutterEngine) {
        super.configureFlutterEngine(engine)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        ble = BridgeBle(applicationContext) { row -> runOnUiThread { sink?.success(row) } }
        EventChannel(engine.dartExecutor.binaryMessenger, "pl.pactobridge/events")
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink) { sink = events }
                override fun onCancel(arguments: Any?) { sink = null; ble.stop() }
            })
        MethodChannel(engine.dartExecutor.binaryMessenger, "pl.pactobridge/ble")
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "permissions" -> {
                            if (pending != null) result.error("busy", "Trwa prośba o uprawnienia", null)
                            else if (permissions.any { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }) {
                                pending = result; requestPermissions(permissions, 42)
                            } else result.success(ble.capabilities())
                        }
                        "capabilities" -> result.success(ble.capabilities())
                        "scan" -> { requirePermissions(); ble.scan(); result.success(null) }
                        "probeGatt" -> { requirePermissions(); ble.probeGatt(); result.success(null) }
                        "probeRadio" -> { requirePermissions(); ble.probeRadio(); result.success(null) }
                        "prepareReceiver" -> { requirePermissions(); ble.prepareReceiver(call.argument<String>("transport") ?: "wifi"); result.success(null) }
                        "connectSession" -> {
                            requirePermissions()
                            ble.connectSession(call.argument<String>("address") ?: "",
                                call.argument<Boolean>("stopped") == true,call.argument<Boolean>("operatorPresent") == true)
                            result.success(null)
                        }
                        // Native interlock is independent of the disabled Flutter button.
                        "connect" -> { requirePermissions(); ble.connect(call.argument<String>("address") ?: ""); result.success(null) }
                        "stop" -> { ble.stop(); result.success(null) }
                        else -> result.notImplemented()
                    }
                } catch (e: Exception) { result.error("ble", e.message ?: e.javaClass.simpleName, null) }
            }
    }

    private fun requirePermissions() {
        check(permissions.all { checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }) {
            "Najpierw wybierz Sprawdź telefon i uprawnienia."
        }
    }

    override fun onRequestPermissionsResult(code: Int, names: Array<out String>, grants: IntArray) {
        super.onRequestPermissionsResult(code, names, grants)
        if (code != 42) return
        val result = pending; pending = null
        if (permissions.all { checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }) {
            try { result?.success(ble.capabilities()) }
            catch (e: Exception) { result?.error("ble", e.message, null) }
        } else result?.error("permissions", "Odmówiono uprawnień Urządzenia w pobliżu. Włącz je w ustawieniach aplikacji.", null)
    }

    override fun onStop() {
        if (::ble.isInitialized) ble.stop()
        super.onStop()
    }
    override fun onDestroy() {
        if (::ble.isInitialized) ble.stop()
        pending?.error("closed", "Aplikacja zamknięta", null); pending = null
        super.onDestroy()
    }
}
