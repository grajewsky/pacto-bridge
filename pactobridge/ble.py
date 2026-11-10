"""BLE central: select FFF1/FFF2 by GATT properties under FFF0; no DFU."""
import asyncio
import logging
import time

from .polling import get_profile
from .safety import require_live_connection
from .uuids import FFF1, FFF2, VENDOR_CHANNELS, VENDOR_SERVICE, uuid16

log = logging.getLogger(__name__)
TARGET_NAME = "iConsole+0106"


async def discover(timeout: float = 10.0):
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    return sorted(found.values(), key=lambda pair: (
        pair[1].local_name != TARGET_NAME, pair[1].local_name or pair[0].name or ""))


class Treadmill:
    def __init__(self, recorder, emit, *, address=None, name=TARGET_NAME,
                 polling=None, timeout=15.0, silence_timeout=20.0,
                 scanner=None, client_factory=None, diagnostics=False):
        self.recorder = recorder
        self.emit = emit
        self.address = address
        self.name = name
        self.profile = get_profile(polling)
        self.diagnostics = diagnostics
        if diagnostics and polling != "pacto-status":
            raise ValueError("Diagnostics require the verified pacto-status profile")
        self.timeout = timeout
        self.silence_timeout = silence_timeout
        self.scanner = scanner or discover
        self.client_factory = client_factory

    def event(self, kind, **fields):
        row = self.recorder.event(kind, **fields)
        log.info(kind, extra={"event": row})
        self.emit(row)

    async def run(self):
        require_live_connection()
        if self.client_factory is None:
            from bleak import BleakClient
            self.client_factory = BleakClient
        backoff = 1.0
        while True:
            session_started = False
            try:
                self.event("status", state="scanning")
                devices = await asyncio.wait_for(self.scanner(), self.timeout)
                matches = [(d, adv) for d, adv in devices if (
                    d.address == self.address if self.address else
                    (adv.local_name or d.name) == self.name)]
                if not matches:
                    raise ConnectionError("Target not found; turn on the treadmill and close other BLE apps")
                if len(matches) != 1:
                    raise ConnectionError("Multiple matching treadmills; select a device identifier")
                device, adv = matches[0]
                if self.profile and self.profile.device_name != (adv.local_name or device.name):
                    raise ConnectionError("Read-only polling profile does not match this device name")
                self.event("status", state="connecting", address=device.address,
                           name=adv.local_name or device.name)
                async with self.client_factory(device, timeout=self.timeout) as client:
                    session_started = True
                    await self.session(client)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.event("error", message=f"{type(exc).__name__}: {exc}")
            if self.diagnostics and session_started:
                # One diagnostic session compares both supported write modes;
                # don't repeatedly probe the device after a conclusive result.
                return
            self.event("status", state="reconnecting", retry_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def read_device_info(self, client):
        service = client.services.get_service(uuid16(0x180A))
        # These are the only two value reads observed before A0 in Android.
        for name, uuid in (("firmware_revision", uuid16(0x2A26)),
                           ("hardware_revision", uuid16(0x2A27))):
            characteristic = next((c for c in service.characteristics if c.uuid.lower() == uuid), None) if service else None
            if characteristic is None or "read" not in characteristic.properties:
                self.event("device_info", field=name, characteristic=uuid, available=False)
                continue
            try:
                value = bytes(await asyncio.wait_for(client.read_gatt_char(characteristic), self.timeout))
                self.event("device_info", field=name, characteristic=uuid, available=True,
                           hex=value.hex(" "), text=value.decode("utf-8", errors="backslashreplace"))
            except Exception as exc:
                self.event("device_info", field=name, characteristic=uuid, available=False,
                           error=f"{type(exc).__name__}: {exc}")

    async def session(self, client):
        for service in client.services:
            self.event("gatt", service=service.uuid, characteristics=[
                {"uuid": c.uuid, "properties": list(c.properties), "handle": c.handle}
                for c in service.characteristics])
        vendor = client.services.get_service(VENDOR_SERVICE)
        if vendor is None:
            raise ConnectionError("FFF0 service missing")
        channels = [c for c in vendor.characteristics if c.uuid.lower() in VENDOR_CHANNELS]
        notifications = [c for c in channels if "notify" in c.properties]
        if len(notifications) != 1:
            raise ConnectionError("Expected exactly one FFF1/FFF2 notify characteristic under FFF0")
        notify = notifications[0]
        if self.profile and (notify.uuid.lower() != FFF1
                             or not any(c.uuid.lower() == FFF2
                                        and "write-without-response" in c.properties for c in channels)):
            raise ConnectionError("Pacto polling requires observed FFF1 notify / FFF2 write layout")
        self.event("channels", service=vendor.uuid, notify=notify.uuid.lower(),
                   write_candidates=[c.uuid.lower() for c in channels
                                     if {"write", "write-without-response"}.intersection(c.properties)])
        last_packet = time.monotonic()
        warned = False
        callback_error = None
        identified = asyncio.Event()
        identification_buffer = bytearray()

        def receive(char, data):
            nonlocal last_packet, warned, callback_error
            last_packet = time.monotonic()
            warned = False
            try:
                self.event("notification", service=VENDOR_SERVICE,
                           characteristic=char.uuid.lower(), hex=bytes(data).hex(" "))
                if self.profile and self.profile.identify_response and not identified.is_set():
                    expected = self.profile.identify_response
                    identification_buffer.extend(data)
                    if expected in identification_buffer:
                        identified.set()
                    # Allow a reply split across notifications, retaining only
                    # its possible incomplete prefix. Other replies are logged.
                    del identification_buffer[:max(0, len(identification_buffer) - len(expected) + 1)]
            except Exception as exc:
                callback_error = exc

        try:
            await asyncio.wait_for(client.start_notify(notify, receive), self.timeout)
            self.event("status", state="subscribed", characteristic=notify.uuid.lower(),
                       message="Subscribed to treadmill telemetry")
            write = None
            if self.profile:
                transport_response = self.profile.response
                required = "write" if self.profile.response else "write-without-response"
                writable = [c for c in channels if required in c.properties]
                if len(writable) != 1:
                    raise ConnectionError("Verified polling requires exactly one vendor write channel")
                write = writable[0]

                async def send(request, purpose, response=None):
                    mode = transport_response if response is None else response
                    required = "write" if mode else "write-without-response"
                    if required not in write.properties:
                        raise ConnectionError(f"Selected vendor channel does not support {required}")
                    self.event("write", characteristic=write.uuid.lower(), hex=request.hex(" "),
                               evidence=self.profile.evidence, purpose=purpose, response=mode)
                    try:
                        await asyncio.wait_for(client.write_gatt_char(
                            write, request, response=mode), self.timeout)
                    except Exception as exc:
                        self.event("write_result", purpose=purpose, response=mode, success=False,
                                   error=f"{type(exc).__name__}: {exc}")
                        raise
                    self.event("write_result", purpose=purpose, response=mode, success=True)

                if self.profile.identify_request:
                    if self.diagnostics:
                        await self.read_device_info(client)
                    if self.profile.notify_settle_s:
                        self.event("status", state="settling", delay_s=self.profile.notify_settle_s,
                                   message="Allowing captured notification setup delay")
                        await asyncio.sleep(self.profile.notify_settle_s)
                    self.event("status", state="identifying",
                               message="Waiting for captured Pacto identification reply")
                    modes = [self.profile.response]
                    if self.diagnostics and "write" in write.properties and "write-without-response" in write.properties:
                        modes.append(not self.profile.response)
                    for mode in modes:
                        try:
                            await send(self.profile.identify_request, "identification", response=mode)
                            await asyncio.wait_for(identified.wait(), self.timeout)
                        except Exception as exc:
                            if self.diagnostics:
                                self.event("probe_result", response=mode, identified=False,
                                           error=f"{type(exc).__name__}: {exc}")
                            continue
                        transport_response = mode
                        if self.diagnostics:
                            self.event("probe_result", response=mode, identified=True)
                        break
                    else:
                        raise ConnectionError(
                            "Pacto identification reply missing or mismatched; no status polls sent")
                    self.event("status", state="identified", response=transport_response,
                               message="Pacto 01/D3 identification confirmed")
            next_poll = time.monotonic()
            while client.is_connected:
                if callback_error:
                    raise callback_error
                now = time.monotonic()
                if not warned and now - last_packet >= self.silence_timeout:
                    self.event("warning", characteristic=notify.uuid.lower(),
                               message=("No vendor telemetry received. Full app initialization is not enabled; "
                                        + ("read-only status polling is active." if self.profile else "passive capture is active.")))
                    warned = True
                if self.profile and now >= next_poll:
                    for request in self.profile.requests:
                        await send(request, "status")
                    next_poll = now + self.profile.interval_s
                await asyncio.sleep(0.2)
        finally:
            if client.is_connected:
                try:
                    await asyncio.wait_for(client.stop_notify(notify), self.timeout)
                except Exception:
                    log.warning("Notification cleanup failed", exc_info=True)
            self.event("status", state="disconnected")
