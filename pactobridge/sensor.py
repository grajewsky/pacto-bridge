"""RSC encoding and optional peripheral transport, gated on verified live input."""
import asyncio
import math
import struct
import time

from .protocols import VERIFIED_DECODERS
from .uuids import RSC_SERVICE, RSC_MEASUREMENT, RSC_FEATURE


def encode_rsc(kmh: float) -> bytes:
    if not math.isfinite(kmh) or kmh < 0:
        raise ValueError("Speed must be finite and nonnegative")
    units = round(kmh / 3.6 * 256)
    if units > 65535:
        raise ValueError("Speed exceeds RSC uint16 range")
    # No stride/distance/status features. Cadence is mandatory in RSC; 0 is
    # an unavailable placeholder, never a source for speed estimation.
    return struct.pack("<BHB", 0, units, 0)


class RunningSensor:
    def __init__(self, decoder_name: str, *, stale_after=3.0, server_factory=None):
        if decoder_name not in VERIFIED_DECODERS:
            raise ValueError("Advertising disabled: no verified Pacto live decoder")
        if not math.isfinite(stale_after) or stale_after <= 0:
            raise ValueError("stale_after must be positive")
        self.stale_after = stale_after
        self.server_factory = server_factory
        self.latest = None
        self.sample_time = None

    def update(self, kmh):
        self.latest = encode_rsc(kmh)
        self.sample_time = time.monotonic()

    def invalidate(self):
        self.latest = None
        self.sample_time = None

    def fresh(self):
        return (self.latest is not None and self.sample_time is not None
                and time.monotonic() - self.sample_time < self.stale_after)

    async def run(self):
        from bless import BlessServer, GATTCharacteristicProperties as Props
        from bless import GATTAttributePermissions as Perms
        factory = self.server_factory or BlessServer
        server = factory(name="PactoBridge", loop=asyncio.get_running_loop())
        server.read_request_func = lambda characteristic, **kwargs: characteristic.value
        active = False
        try:
            await server.add_new_service(RSC_SERVICE)
            await server.add_new_characteristic(RSC_SERVICE, RSC_MEASUREMENT,
                                                Props.notify, None, Perms.readable)
            await server.add_new_characteristic(RSC_SERVICE, RSC_FEATURE,
                                                Props.read, bytearray(b"\x00\x00"), Perms.readable)
            while True:
                if self.fresh():
                    server.get_characteristic(RSC_MEASUREMENT).value = bytearray(self.latest)
                    if not active:
                        await server.start()
                        active = True
                    server.update_value(RSC_SERVICE, RSC_MEASUREMENT)
                elif active:
                    # Stop broadcasting stale speed. Unknown is never zero.
                    await server.stop()
                    active = False
                await asyncio.sleep(0.25)
        finally:
            await server.stop()
