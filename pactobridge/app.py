"""Live orchestration. Replay has no sensor path."""
import asyncio
from .ble import Treadmill
from .protocols import decoder_for
from .recording import Recorder
from .sensor import RunningSensor
from .safety import require_live_connection
from .uuids import VENDOR_CHANNELS, VENDOR_SERVICE


async def capture(path, emit, *, address=None, name="iConsole+0106", polling=None,
                  decoder_name="raw", advertise=False, diagnostics=False):
    require_live_connection()
    decoder = decoder_for(decoder_name, live=True)
    sensor = RunningSensor(decoder_name) if advertise else None
    with Recorder(path) as recorder:
        recorder.event("session", app="PactoBridge", decoder=decoder_name,
                       polling=polling, advertise=advertise, diagnostics=diagnostics)

        def receive(row):
            emit(row)
            if row["kind"] == "status" and row["state"] in (
                    "disconnected", "reconnecting", "connecting"):
                decoder.reset()
                if sensor:
                    sensor.invalidate()
                emit({"kind": "speed_unavailable"})
            if (row["kind"] == "notification"
                    and row["characteristic"].lower() in VENDOR_CHANNELS
                    and row.get("service", VENDOR_SERVICE).lower() == VENDOR_SERVICE):
                for speed in decoder.feed(bytes.fromhex(row["hex"])):
                    emit({"kind": "speed", "kmh": speed.kmh, "verified": True})
                    if sensor:
                        sensor.update(speed.kmh)

        treadmill = Treadmill(recorder, receive, address=address, name=name, polling=polling,
                              diagnostics=diagnostics)
        tasks = [asyncio.create_task(treadmill.run())]
        if sensor:
            tasks.append(asyncio.create_task(sensor.run()))
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            recorder.event("session_end")
