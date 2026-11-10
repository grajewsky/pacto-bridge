@file:Suppress("DEPRECATION", "MissingPermission")
package pl.pactobridge.pacto_bridge

import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.UUID

/** Separate custom service: never impersonates an RSC sensor or sends speed. */
internal class RadioProbe(private val context: Context, private val emit: (Map<String, Any?>) -> Unit) {
    private val manager = context.getSystemService(BluetoothManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private val serviceId = UUID.fromString("9260b100-2460-4ce3-956a-f1a3d6e086f1")
    private val valueId = UUID.fromString("9260b101-2460-4ce3-956a-f1a3d6e086f1")
    private val payload = "PB-RADIO-1".toByteArray(Charsets.US_ASCII)
    private var server: BluetoothGattServer? = null
    private var callback: AdvertiseCallback? = null
    private var epoch = 0
    private val clients = HashMap<String, BluetoothDevice>()
    private fun message(s: String) = emit(mapOf("kind" to "status", "message" to s))

    fun start() {
        stop()
        val adapter = manager.adapter
        check(adapter?.isEnabled == true && adapter.bluetoothLeAdvertiser != null) { "Brak nadajnika BLE." }
        val token = epoch
        val gattCallback = object : BluetoothGattServerCallback() {
            override fun onServiceAdded(status: Int, service: BluetoothGattService) {
                handler.post {
                    if (token != epoch) return@post
                    if (status != BluetoothGatt.GATT_SUCCESS) { stop(); message("Błąd usługi diagnostycznej: $status"); return@post }
                    val adv = object : AdvertiseCallback() {
                        override fun onStartSuccess(settings: AdvertiseSettings) { handler.post {
                            if (token == epoch) message("Test radia BLE aktywny przez 60 s. Osobna usługa diagnostyczna; bez prędkości i bez RSC.")
                        } }
                        override fun onStartFailure(code: Int) { handler.post {
                            if (token == epoch) { stop(); message("Błąd reklamy diagnostycznej: $code") }
                        } }
                    }
                    callback = adv
                    try { adapter.bluetoothLeAdvertiser.startAdvertising(
                        AdvertiseSettings.Builder().setConnectable(true).setTimeout(0)
                            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY).build(),
                        AdvertiseData.Builder().addServiceUuid(ParcelUuid(serviceId)).setIncludeDeviceName(false).build(), adv)
                    } catch (e: Exception) { stop(); message("Błąd testu radia: ${e.message}") }
                }
            }
            override fun onConnectionStateChange(device: BluetoothDevice, status: Int, newState: Int) { handler.post {
                if (token != epoch) return@post
                // Android also reports pre-existing, unrelated LE links here.
                // Own only peers that actually read/subscribe to this service.
                if (status != BluetoothGatt.GATT_SUCCESS || newState == BluetoothProfile.STATE_DISCONNECTED)
                    clients.remove(device.address)
            } }
            override fun onCharacteristicReadRequest(device: BluetoothDevice, id: Int, offset: Int, c: BluetoothGattCharacteristic) { handler.post {
                if (token != epoch) return@post
                if (c.uuid != valueId) server?.sendResponse(device,id,BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED,offset,null)
                else if (offset !in 0..payload.size) server?.sendResponse(device,id,BluetoothGatt.GATT_INVALID_OFFSET,offset,null)
                else {
                    clients[device.address] = device
                    server?.sendResponse(device,id,BluetoothGatt.GATT_SUCCESS,offset,payload.copyOfRange(offset,payload.size))
                }
            } }
            override fun onDescriptorWriteRequest(device: BluetoothDevice, id: Int, d: BluetoothGattDescriptor,
                prepared: Boolean, response: Boolean, offset: Int, value: ByteArray) { handler.post {
                if (token != epoch) return@post
                val enable = value.contentEquals(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                val disable = value.contentEquals(BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE)
                val valid = !prepared && offset == 0 && d.uuid == uuid("2902") && d.characteristic.uuid == valueId && (enable || disable)
                if (response) server?.sendResponse(device,id,if (valid) BluetoothGatt.GATT_SUCCESS else BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED,offset,null)
                if (valid && enable) {
                    clients[device.address] = device
                    handler.postDelayed({
                    if (token == epoch && device.address in clients) {
                        d.characteristic.value = payload
                        server?.notifyCharacteristicChanged(device,d.characteristic,false)
                    }
                    }, 300)
                }
            } }
            override fun onNotificationSent(device: BluetoothDevice, status: Int) { handler.post {
                if (token == epoch) message("Potwierdzenie wysłania powiadomienia diagnostycznego: $status")
            } }
        }
        val g = manager.openGattServer(context,gattCallback) ?: error("Nie udało się otworzyć serwera diagnostycznego.")
        server = g
        val service = BluetoothGattService(serviceId,BluetoothGattService.SERVICE_TYPE_PRIMARY)
        val c = BluetoothGattCharacteristic(valueId,BluetoothGattCharacteristic.PROPERTY_READ or BluetoothGattCharacteristic.PROPERTY_NOTIFY,
            BluetoothGattCharacteristic.PERMISSION_READ)
        c.value = payload
        c.addDescriptor(BluetoothGattDescriptor(uuid("2902"),BluetoothGattDescriptor.PERMISSION_WRITE))
        service.addCharacteristic(c)
        if (!g.addService(service)) { stop(); error("Rejestracja testu radia odrzucona.") }
        handler.postDelayed({ if (token == epoch) { stop(); message("Test radia zakończony; reklama i połączenia zamknięte.") } },60000)
    }

    fun stop() {
        epoch++
        callback?.let { try { manager.adapter?.bluetoothLeAdvertiser?.stopAdvertising(it) } catch (_: Exception) { } }
        callback = null
        server?.let { g ->
            clients.values.forEach { try { g.cancelConnection(it) } catch (_: Exception) { } }
            try { g.close() } catch (_: Exception) { }
        }
        server = null; clients.clear()
    }
}
