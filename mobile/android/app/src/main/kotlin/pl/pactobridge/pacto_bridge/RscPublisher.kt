@file:Suppress("DEPRECATION", "MissingPermission")
package pl.pactobridge.pacto_bridge

import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.os.SystemClock
import java.util.UUID

/** No Flutter publish-speed method: only the native live receiver owns this sink. */
internal class RscPublisher(private val context: Context, private val emit: (Map<String, Any?>) -> Unit) : LivePublisher {
    private val manager = context.getSystemService(BluetoothManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private val serviceId = uuid("1814")
    private val measurementId = uuid("2a53")
    private val featureId = uuid("2a54")
    private val cccdId = uuid("2902")
    private val identityServiceId = UUID.fromString("9260b200-2460-4ce3-956a-f1a3d6e086f1")
    private val identityValueId = UUID.fromString("9260b201-2460-4ce3-956a-f1a3d6e086f1")
    private val identityValue = "PB-PACTO-LIVE-1".toByteArray(Charsets.US_ASCII)
    private var server: BluetoothGattServer? = null
    private var measurement: BluetoothGattCharacteristic? = null
    private var advertiserCallback: AdvertisingSetCallback? = null
    private var advertisingSet: AdvertisingSet? = null
    private var epoch = 0
    private var ready = false
    private var latest: ByteArray? = null
    private val order = ReceiverOrderGate { SystemClock.elapsedRealtime() }
    private val subscribers = HashMap<String, BluetoothDevice>()
    private val clients = HashMap<String, BluetoothDevice>()
    private val pending = HashSet<String>()

    private fun fresh(): Boolean = order.fresh()
    private fun message(text: String) = emit(mapOf("kind" to "status", "message" to text))

    override fun requireReceiver() = order.requireReceiver()
    override fun canWaitForSource(): Boolean = order.phase==ReceiverOrderGate.Phase.RECEIVER_READY &&
        order.preparing() && subscribers.keys.any { order.isPeer(it) }

    fun prepareReceiver() {
        stop(); requirePeripheral(); order.prepare(); open(false)
        emit(mapOf("kind" to "transport_state", "state" to "WAITING_RECEIVER",
            "message" to "Połącz Zwift jako odbiornik prędkości. RSC jest widoczne, ale bez pomiarów do czasu odczytu Pacto."))
    }

    fun probe() {
        stop()
        requirePeripheral()
        open(true)
        message("Sprawdzanie rejestracji usługi RSC; bez reklamowania i bez prędkości testowej.")
        val token = epoch
        handler.postDelayed({ if (token == epoch && server != null) {
            stop(); message("Przekroczony czas rejestracji RSC.")
        } }, 5000)
    }

    private fun requirePeripheral() {
        val adapter = manager.adapter
        check(adapter?.isEnabled == true) { "Włącz Bluetooth." }
        check(adapter.isMultipleAdvertisementSupported && adapter.bluetoothLeAdvertiser != null) {
            "Telefon nie zgłasza obsługi nadawania BLE."
        }
    }

    override fun onLiveMeasurement(tenthsKmh: Int) {
        // The receiver has already validated the B2 payload and connection epoch.
        val packet = try { rscPacket(tenthsKmh) } catch (_: IllegalArgumentException) {
            stop(); message("Telemetria przekracza zakres pomiaru RSC."); return
        }
        try { order.sample() } catch (e: IllegalStateException) { stop(); message(e.message ?: "Błąd kolejności połączeń"); return }
        latest = packet
        if (server == null) {
            try { requirePeripheral(); open(false) }
            catch (e: Exception) { stop(); message(e.message ?: "Błąd nadajnika"); return }
        }
        if (ready) advertise()
        handler.removeCallbacks(tick)
        handler.post(tick)
    }

    private val tick = object : Runnable {
        override fun run() {
            if (!fresh()) {
                stop(); emit(mapOf("kind" to "unavailable"))
                message("Brak świeżej telemetrii: nadajnik i połączenia Zwift zamknięte.")
                return
            }
            if (ready) {
                val bytes = latest ?: return
                val c = measurement ?: return
                c.value = bytes
                for ((address, device) in subscribers.toMap()) {
                    if (address !in pending) {
                        pending.add(address)
                        val accepted = try { server?.notifyCharacteristicChanged(device, c, false) == true }
                            catch (_: Exception) { false }
                        if (!accepted) pending.remove(address)
                    }
                }
            }
            handler.postDelayed(this, 250)
        }
    }

    private fun open(probe: Boolean) {
        val token = ++epoch
        val callback = object : BluetoothGattServerCallback() {
            override fun onServiceAdded(status: Int, service: BluetoothGattService) {
                handler.post {
                    if (token != epoch) return@post
                    if (status != BluetoothGatt.GATT_SUCCESS) {
                        stop(); message("Rejestracja usługi RSC nie powiodła się: $status")
                    } else if (service.uuid == serviceId) {
                        val identity = BluetoothGattService(identityServiceId, BluetoothGattService.SERVICE_TYPE_PRIMARY)
                        val value = BluetoothGattCharacteristic(identityValueId, BluetoothGattCharacteristic.PROPERTY_READ,
                            BluetoothGattCharacteristic.PERMISSION_READ)
                        value.value = identityValue
                        identity.addCharacteristic(value)
                        if (server?.addService(identity) != true) { stop(); message("Błąd rejestracji identyfikatora mostu.") }
                    } else if (service.uuid != identityServiceId) {
                        stop(); message("Nieoczekiwana usługa podczas rejestracji czujnika.")
                    } else if (probe) {
                        stop(); message("Usługa RSC zarejestrowana poprawnie. Test nie nadawał danych. Zwift jeszcze niezweryfikowany.")
                    } else {
                        ready = true
                        if (fresh() || order.preparing()) advertise() else stop()
                    }
                }
            }
            override fun onConnectionStateChange(device: BluetoothDevice, status: Int, newState: Int) {
                handler.post {
                    if (token != epoch) return@post
                    if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) {
                        // Existing ACL links (including the treadmill) are not
                        // necessarily clients of this GATT server.
                    } else {
                        clients.remove(device.address); subscribers.remove(device.address); pending.remove(device.address)
                        if (order.isPeer(device.address) && order.preparing()) {
                            stop(); message("Odbiornik PC rozłączony przed rozpoczęciem sesji.")
                        }
                    }
                }
            }
            override fun onCharacteristicReadRequest(device: BluetoothDevice, id: Int, offset: Int,
                                                       c: BluetoothGattCharacteristic) {
                handler.post {
                    if (token != epoch) return@post
                    val value = when (c.uuid) { featureId -> byteArrayOf(0,0); identityValueId -> identityValue; else -> null }
                    if (value != null) clients[device.address] = device
                    if (value == null) respond(device, id, BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED, offset, null)
                    else if (offset !in 0..value.size) respond(device, id, BluetoothGatt.GATT_INVALID_OFFSET, offset, null)
                    else {
                        val sent=respond(device, id, BluetoothGatt.GATT_SUCCESS, offset, value.copyOfRange(offset,value.size))
                        if (!sent) message("Nie wysłano odpowiedzi odczytu GATT.")
                    }
                }
            }
            override fun onDescriptorReadRequest(device: BluetoothDevice, id: Int, offset: Int, d: BluetoothGattDescriptor) {
                handler.post {
                    if (token != epoch) return@post
                    if (d.uuid != cccdId) respond(device,id,BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED,offset,null)
                    else if (offset !in 0..2) respond(device,id,BluetoothGatt.GATT_INVALID_OFFSET,offset,null)
                    else {
                        val value = byteArrayOf(if (device.address in subscribers) 1 else 0, 0)
                        respond(device,id,BluetoothGatt.GATT_SUCCESS,offset,value.copyOfRange(offset,2))
                    }
                }
            }
            override fun onDescriptorWriteRequest(device: BluetoothDevice, id: Int, d: BluetoothGattDescriptor,
                prepared: Boolean, response: Boolean, offset: Int, value: ByteArray) {
                handler.post {
                    if (token != epoch) return@post
                    var status = BluetoothGatt.GATT_SUCCESS
                    if (prepared || d.uuid != cccdId || d.characteristic.uuid != measurementId)
                        status = BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED
                    else if (offset != 0) status = BluetoothGatt.GATT_INVALID_OFFSET
                    else if (value.contentEquals(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)) {
                        clients[device.address] = device
                        subscribers[device.address] = device
                        message("Odbiornik zasubskrybował rzeczywisty pomiar RSC.")
                    }
                    else if (value.contentEquals(BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE))
                        subscribers.remove(device.address)
                    else status = BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED
                    val accepted = !response || respond(device,id,status,offset,null)
                    if (accepted && status==BluetoothGatt.GATT_SUCCESS &&
                        value.contentEquals(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) &&
                        order.confirmReceiver(device.address)) {
                        emit(mapOf("kind" to "transport_state", "state" to "RECEIVER_READY",
                            "message" to "Odbiornik RSC połączony. Przygotuj teraz Pacto na postoju."))
                    }
                }
            }
            override fun onCharacteristicWriteRequest(device: BluetoothDevice, id: Int,
                c: BluetoothGattCharacteristic, prepared: Boolean, response: Boolean, offset: Int, value: ByteArray) {
                handler.post { if (token == epoch && response)
                    respond(device,id,BluetoothGatt.GATT_WRITE_NOT_PERMITTED,offset,null) }
            }
            override fun onExecuteWrite(device: BluetoothDevice, id: Int, execute: Boolean) {
                handler.post { if (token == epoch) respond(device,id,BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED,0,null) }
            }
            override fun onNotificationSent(device: BluetoothDevice, status: Int) {
                handler.post { if (token == epoch) pending.remove(device.address) }
            }
        }
        val gatt = manager.openGattServer(context, callback)
            ?: throw IllegalStateException("Android nie otworzył serwera GATT.")
        server = gatt
        val service = BluetoothGattService(serviceId, BluetoothGattService.SERVICE_TYPE_PRIMARY)
        val c = BluetoothGattCharacteristic(measurementId, BluetoothGattCharacteristic.PROPERTY_NOTIFY, 0)
        c.addDescriptor(BluetoothGattDescriptor(cccdId,
            BluetoothGattDescriptor.PERMISSION_READ or BluetoothGattDescriptor.PERMISSION_WRITE))
        measurement = c
        service.addCharacteristic(c)
        val feature = BluetoothGattCharacteristic(featureId, BluetoothGattCharacteristic.PROPERTY_READ,
            BluetoothGattCharacteristic.PERMISSION_READ)
        feature.value = byteArrayOf(0,0)
        service.addCharacteristic(feature)
        if (!gatt.addService(service)) { stop(); throw IllegalStateException("Android odrzucił usługę RSC.") }
    }

    private fun respond(device: BluetoothDevice, id: Int, status: Int, offset: Int, value: ByteArray?): Boolean {
        return try { server?.sendResponse(device,id,status,offset,value)==true } catch (_: Exception) { false }
    }

    private fun advertise() {
        if ((!fresh() && !order.preparing()) || !ready) return
        if (advertiserCallback!=null) return
        // Discoverable by an unmodified Zwift client before the central link opens.
        // Registering/advertising RSC never supplies a measurement: only B2 does.
        // Put the standard sensor and existing phone name in the primary packet:
        // some receivers do not collect scan responses. No global Bluetooth rename.
        val data=AdvertiseData.Builder().addServiceUuid(ParcelUuid(serviceId))
            .setIncludeDeviceName(true).build()
        val scanResponse=AdvertiseData.Builder().addServiceUuid(ParcelUuid(identityServiceId)).build()
        val token = epoch
        val callback = object : AdvertisingSetCallback() {
            override fun onAdvertisingSetStarted(set: AdvertisingSet?, txPower: Int, status: Int) {
                handler.post { if (token == epoch) {
                    if (status!=ADVERTISE_SUCCESS || set==null) { stop(); message("Błąd reklamy BLE: $status"); return@post }
                    advertisingSet=set
                    if (fresh()) message("Nadawanie usługi prędkości RSC włączone.")
                    else if (order.preparing()) message("RSC widoczne dla Zwift; oczekiwanie na odbiornik, bez pomiarów.")
                    else stop()
                } }
            }
        }
        advertiserCallback = callback
        // Preserve the receiver link and advertisement when actual source data arrives.
        val settings=AdvertisingSetParameters.Builder().setLegacyMode(true).setConnectable(true).setScannable(true)
            .setInterval(AdvertisingSetParameters.INTERVAL_LOW).setTxPowerLevel(AdvertisingSetParameters.TX_POWER_MEDIUM).build()
        try { manager.adapter.bluetoothLeAdvertiser.startAdvertisingSet(settings,data,scanResponse,null,null,callback) }
        catch (e: Exception) { stop(); message(e.message ?: "Błąd nadawania") }
    }

    override fun stop() {
        epoch++
        handler.removeCallbacks(tick)
        advertiserCallback?.let {
            try { manager.adapter?.bluetoothLeAdvertiser?.stopAdvertisingSet(it) } catch (_: Exception) { }
        }
        advertiserCallback = null
        val g = server; server = null
        if (g != null) {
            for (d in clients.values) { try { g.cancelConnection(d) } catch (_: Exception) { } }
            try { g.close() } catch (_: Exception) { }
        }
        ready = false; latest = null; order.reset(); measurement = null
        advertisingSet=null
        clients.clear(); subscribers.clear(); pending.clear()
        emit(mapOf("kind" to "transport_state", "state" to "INACTIVE"))
    }
}
