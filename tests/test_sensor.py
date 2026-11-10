import asyncio
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from pactobridge.sensor import RunningSensor
from pactobridge.uuids import RSC_MEASUREMENT


class SensorTests(unittest.IsolatedAsyncioTestCase):
    def make_sensor(self, **kwargs):
        # Test-only registration; production registry stays empty.
        with patch.dict('pactobridge.sensor.VERIFIED_DECODERS', {'test': object}):
            return RunningSensor('test', **kwargs)

    async def test_freshness_unknown_zero_and_disconnect(self):
        sensor = self.make_sensor()
        self.assertFalse(sensor.fresh())
        sensor.update(0)
        self.assertTrue(sensor.fresh())
        sensor.sample_time = time.monotonic() - 4
        self.assertFalse(sensor.fresh())
        sensor.invalidate()
        self.assertIsNone(sensor.latest)
        self.assertFalse(sensor.fresh())

    async def test_peripheral_waits_stops_stale_and_restarts(self):
        characteristic = SimpleNamespace(value=None)
        server = SimpleNamespace(add_new_service=AsyncMock(), add_new_characteristic=AsyncMock(),
                                 start=AsyncMock(), stop=AsyncMock(), update_value=Mock(),
                                 get_characteristic=Mock(return_value=characteristic))
        sensor = self.make_sensor(server_factory=lambda **kwargs: server)
        fake_bless = SimpleNamespace(BlessServer=Mock(),
                                    GATTCharacteristicProperties=SimpleNamespace(notify=1, read=2),
                                    GATTAttributePermissions=SimpleNamespace(readable=1))
        iterations = 0
        async def tick(delay):
            nonlocal iterations
            iterations += 1
            if iterations == 1:
                server.start.assert_not_awaited()
                sensor.update(8)
            elif iterations == 2:
                self.assertEqual(server.start.await_count, 1)
                sensor.sample_time = time.monotonic() - 10
            elif iterations == 3:
                self.assertEqual(server.stop.await_count, 1)
                sensor.update(6)
            else:
                raise asyncio.CancelledError()
        with patch.dict(sys.modules, {'bless': fake_bless}), patch('pactobridge.sensor.asyncio.sleep', side_effect=tick):
            with self.assertRaises(asyncio.CancelledError):
                await sensor.run()
        self.assertEqual(server.start.await_count, 2)
        self.assertEqual(server.stop.await_count, 2)
        self.assertEqual(server.get_characteristic.call_args.args[0], RSC_MEASUREMENT)
        self.assertEqual(server.update_value.call_count, 2)

    async def test_failed_publication_stops_server(self):
        server = SimpleNamespace(add_new_service=AsyncMock(side_effect=RuntimeError('unavailable')),
                                 stop=AsyncMock())
        sensor = self.make_sensor(server_factory=lambda **kwargs: server)
        fake_bless = SimpleNamespace(BlessServer=Mock(), GATTCharacteristicProperties=object,
                                    GATTAttributePermissions=object)
        with patch.dict(sys.modules, {'bless': fake_bless}):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                await sensor.run()
        server.stop.assert_awaited_once()
