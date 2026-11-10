import asyncio
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests import test_ble as ble_fixtures
from pactobridge.polling import get_profile
from pactobridge.uuids import FFF1, FFF2, uuid16


@patch('pactobridge.ble.require_live_connection', new=lambda: None)
class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    setUp = ble_fixtures.BLETests.setUp
    treadmill = ble_fixtures.BLETests.treadmill

    def diagnostic(self, **kwargs):
        profile = replace(get_profile('pacto-status'), notify_settle_s=0)
        with patch.dict('pactobridge.polling.CAPTURED_PROFILES', {'pacto-status': profile}):
            return self.treadmill(polling='pacto-status', diagnostics=True, timeout=0.01, **kwargs)

    def client(self):
        client = ble_fixtures.FakeClient(notifications=False)
        client.notify.uuid = FFF1
        client.service.characteristics.append(SimpleNamespace(
            uuid=FFF2, properties=['write-without-response', 'write'], handle=16))
        client.services.append(SimpleNamespace(uuid=uuid16(0x180A), characteristics=[
            SimpleNamespace(uuid=uuid16(0x2A26), properties=['read'], handle=30),
            SimpleNamespace(uuid=uuid16(0x2A27), properties=['read'], handle=28)]))
        client.read_gatt_char = AsyncMock(side_effect=lambda char:
            b'05' if char.uuid == uuid16(0x2A26) else b'C0.00.C0.00')
        async def subscribe(char, receive):
            client.receive = receive
        client.start_notify.side_effect = subscribe
        return client

    async def test_reads_only_observed_info_and_compares_transport_modes(self):
        client = self.client()
        async def write(char, payload, *, response):
            if payload == bytes.fromhex('f0 a0 01 00 91') and response:
                client.receive(client.notify, bytes.fromhex('f0 b0 01 d3 74'))
            elif payload == bytes.fromhex('f0 a2 01 d3 66'):
                client.is_connected = False
        client.write_gatt_char.side_effect = write
        await self.diagnostic().session(client)
        self.assertEqual([c.args[0].uuid for c in client.read_gatt_char.await_args_list],
                         [uuid16(0x2A26), uuid16(0x2A27)])
        calls = client.write_gatt_char.await_args_list
        self.assertEqual([c.args[1].hex() for c in calls],
                         ['f0a0010091', 'f0a0010091', 'f0a201d366'])
        self.assertEqual([c.kwargs['response'] for c in calls], [False, True, True])
        results = [r for r in self.events if r['kind'] == 'probe_result']
        self.assertEqual([r['identified'] for r in results], [False, True])
        self.assertEqual([r['text'] for r in self.events if r['kind'] == 'device_info'],
                         ['05', 'C0.00.C0.00'])

    async def test_neither_mode_replies_no_status_queries_or_controls(self):
        client = self.client()
        with self.assertRaisesRegex(ConnectionError, 'no status polls sent'):
            await self.diagnostic().session(client)
        self.assertEqual([c.args[1].hex() for c in client.write_gatt_char.await_args_list],
                         ['f0a0010091', 'f0a0010091'])
        client.stop_notify.assert_awaited_once()

    async def test_missing_info_does_not_read_another_service(self):
        client = self.client()
        client.services.pop()
        async def write(char, payload, **kwargs):
            if payload == bytes.fromhex('f0 a0 01 00 91'):
                client.receive(client.notify, bytes.fromhex('f0 b0 01 d3 74'))
            else:
                client.is_connected = False
        client.write_gatt_char.side_effect = write
        await self.diagnostic().session(client)
        client.read_gatt_char.assert_not_awaited()
        self.assertEqual(sum(r['kind'] == 'device_info' and not r['available'] for r in self.events), 2)

    async def test_one_failed_session_does_not_keep_probing(self):
        client = self.client()
        device = SimpleNamespace(address='test', name='iConsole+0106')
        adv = SimpleNamespace(local_name='iConsole+0106')
        scanner = AsyncMock(return_value=[(device, adv)])
        factory = lambda *args, **kwargs: client
        await self.diagnostic(scanner=scanner, client_factory=factory).run()
        self.assertEqual(scanner.await_count, 1)
        self.assertEqual(client.write_gatt_char.await_count, 2)

    async def test_diagnostics_require_verified_profile(self):
        with self.assertRaises(ValueError):
            self.treadmill(diagnostics=True)
