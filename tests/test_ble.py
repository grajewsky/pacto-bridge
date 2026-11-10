import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from pactobridge.ble import Treadmill
from pactobridge.recording import Recorder, read_events
from pactobridge.uuids import FFF1, FFF2, VENDOR_SERVICE


class FakeClient:
    def __init__(self, *, service_uuid=VENDOR_SERVICE, notifications=True):
        self.is_connected = True
        self.notify = SimpleNamespace(uuid=FFF2, properties=['notify'], handle=5)
        self.service = SimpleNamespace(uuid=service_uuid, characteristics=[self.notify])
        class Services(list):
            def get_service(services, uuid):
                return next((s for s in services if s.uuid == uuid), None)
        self.services = Services([self.service])
        self.start_notify = AsyncMock(side_effect=self.subscribe if notifications else None)
        self.stop_notify = AsyncMock()
        self.write_gatt_char = AsyncMock()

    async def subscribe(self, char, callback):
        callback(char, bytearray(b'\x01\x02'))
        self.is_connected = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.is_connected = False


# These simulated transport tests exercise the internal state machine only.
# Real public entry points are tested with the interlock intact in test_safety.
@patch('pactobridge.ble.require_live_connection', new=lambda: None)
class BLETests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'capture.jsonl'
        self.recorder = Recorder(self.path)
        self.addCleanup(self.recorder.close)
        self.events = []

    def treadmill(self, **kwargs):
        return Treadmill(self.recorder, self.events.append, **kwargs)

    async def test_only_fff2_subscription_no_writes(self):
        client = FakeClient()
        await self.treadmill().session(client)
        client.start_notify.assert_awaited_once()
        self.assertEqual(client.start_notify.call_args.args[0].uuid, FFF2)
        client.write_gatt_char.assert_not_awaited()
        notifications = [r for r in read_events(self.path) if r['kind'] == 'notification']
        self.assertEqual(notifications[0]['hex'], '01 02')

    async def test_missing_vendor_service_never_subscribes(self):
        client = FakeClient(service_uuid='dfu')
        with self.assertRaises(ConnectionError):
            await self.treadmill().session(client)
        client.start_notify.assert_not_awaited()
        client.write_gatt_char.assert_not_awaited()

    async def test_observed_pacto_mapping_fff1_notifies_fff2_writes(self):
        # Properties observed in the user's 2026-11-09 GATT capture.
        client = FakeClient()
        client.notify.uuid = FFF1
        client.notify.handle = 17
        client.service.characteristics.append(SimpleNamespace(
            uuid=FFF2, properties=['write-without-response', 'write'], handle=15))
        await self.treadmill().session(client)
        client.start_notify.assert_awaited_once()
        self.assertEqual(client.start_notify.call_args.args[0].uuid, FFF1)
        client.write_gatt_char.assert_not_awaited()
        packet = next(r for r in self.events if r['kind'] == 'notification')
        self.assertEqual(packet['characteristic'], FFF1)
        selected = next(r for r in self.events if r['kind'] == 'channels')
        self.assertEqual(selected['write_candidates'], [FFF2])

    async def test_ambiguous_notification_channels_fail_closed(self):
        client = FakeClient()
        client.service.characteristics.append(SimpleNamespace(
            uuid=FFF1, properties=['notify'], handle=17))
        with self.assertRaises(ConnectionError):
            await self.treadmill().session(client)
        client.start_notify.assert_not_awaited()
        client.write_gatt_char.assert_not_awaited()

    async def test_pacto_polling_identifies_then_sends_observed_status_query(self):
        client = FakeClient(notifications=False)
        client.notify.uuid = FFF1
        write = SimpleNamespace(uuid=FFF2, properties=['write', 'write-without-response'], handle=15)
        client.service.characteristics.append(write)
        callback = None
        async def subscribe(char, receive):
            nonlocal callback
            callback = receive
        client.start_notify.side_effect = subscribe
        async def answered(char, payload, **kwargs):
            if payload == bytes.fromhex('f0 a0 01 00 91'):
                # Expected response can be split across notification packets.
                callback(client.notify, bytes.fromhex('f0 b0 01'))
                callback(client.notify, bytes.fromhex('d3 74'))
            else:
                client.is_connected = False
        client.write_gatt_char.side_effect = answered
        await self.treadmill(polling='pacto-status').session(client)
        self.assertEqual([call.args[1] for call in client.write_gatt_char.await_args_list],
                         [bytes.fromhex('f0 a0 01 00 91'), bytes.fromhex('f0 a2 01 d3 66')])
        self.assertTrue(all(call.kwargs == {'response': False}
                            for call in client.write_gatt_char.await_args_list))
        self.assertTrue(any(r.get('state') == 'identified' for r in self.events))
        settling = next(i for i, r in enumerate(self.events) if r.get('state') == 'settling')
        identify_write = next(i for i, r in enumerate(self.events)
                              if r['kind'] == 'write' and r.get('purpose') == 'identification')
        self.assertLess(settling, identify_write)
        self.assertEqual(self.events[settling]['delay_s'], 1.0)

    async def test_cancel_during_notify_setup_delay_sends_no_protocol_writes(self):
        client = FakeClient(notifications=False)
        client.notify.uuid = FFF1
        client.service.characteristics.append(SimpleNamespace(
            uuid=FFF2, properties=['write-without-response'], handle=15))
        task = asyncio.create_task(self.treadmill(polling='pacto-status').session(client))
        await asyncio.sleep(0.01)
        self.assertTrue(any(r.get('state') == 'settling' for r in self.events))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        client.write_gatt_char.assert_not_awaited()
        client.stop_notify.assert_awaited_once()

    async def test_missing_or_invalid_identification_never_starts_polling(self):
        for reply in (b'', bytes.fromhex('f0 b0 01 d3 75'),
                      bytes.fromhex('f0 b0 02 d3 75')):
            with self.subTest(reply=reply):
                client = FakeClient(notifications=False)
                client.notify.uuid = FFF1
                write = SimpleNamespace(uuid=FFF2, properties=['write-without-response'], handle=15)
                client.service.characteristics.append(write)
                callback = None
                async def subscribe(char, receive):
                    nonlocal callback
                    callback = receive
                async def answered(*args, **kwargs):
                    if reply:
                        callback(client.notify, reply)
                client.start_notify.side_effect = subscribe
                client.write_gatt_char.side_effect = answered
                with self.assertRaisesRegex(ConnectionError, 'no status polls sent'):
                    await self.treadmill(polling='pacto-status', timeout=0.01).session(client)
                client.write_gatt_char.assert_awaited_once_with(
                    write, bytes.fromhex('f0 a0 01 00 91'), response=False)
                client.stop_notify.assert_awaited_once()

    async def test_identification_repeated_on_each_new_session(self):
        for _ in range(2):
            client = FakeClient(notifications=False)
            client.notify.uuid = FFF1
            client.service.characteristics.append(SimpleNamespace(
                uuid=FFF2, properties=['write-without-response'], handle=15))
            callback = None
            async def subscribe(char, receive):
                nonlocal callback
                callback = receive
            async def answered(char, payload, **kwargs):
                if payload == bytes.fromhex('f0 a0 01 00 91'):
                    callback(client.notify, bytes.fromhex('f0 b0 01 d3 74'))
                else:
                    client.is_connected = False
            client.start_notify.side_effect = subscribe
            client.write_gatt_char.side_effect = answered
            await self.treadmill(polling='pacto-status').session(client)
            self.assertEqual(client.write_gatt_char.await_args_list[0].args[1],
                             bytes.fromhex('f0 a0 01 00 91'))

    async def test_active_polling_refuses_unobserved_gatt_layout(self):
        client = FakeClient()
        with self.assertRaises(ConnectionError):
            await self.treadmill(polling='pacto-status').session(client)
        client.start_notify.assert_not_awaited()
        client.write_gatt_char.assert_not_awaited()

    async def test_polling_cannot_be_applied_to_another_device(self):
        device = SimpleNamespace(address='test', name='Other')
        adv = SimpleNamespace(local_name='Other')
        factory = AsyncMock()
        treadmill = self.treadmill(address='test', polling='pacto-status',
                                  scanner=AsyncMock(return_value=[(device, adv)]), client_factory=factory)
        with patch('pactobridge.ble.asyncio.sleep', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await treadmill.run()
        factory.assert_not_called()

    async def test_write_channel_never_used_as_notification_fallback(self):
        client = FakeClient()
        client.notify.properties = ['write', 'write-without-response']
        with self.assertRaises(ConnectionError):
            await self.treadmill().session(client)
        client.start_notify.assert_not_awaited()
        client.write_gatt_char.assert_not_awaited()

    async def test_silence_and_cancellation_cleanup(self):
        client = FakeClient(notifications=False)
        task = asyncio.create_task(self.treadmill(silence_timeout=0).session(client))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        client.stop_notify.assert_awaited_once()
        self.assertTrue(any(r['kind'] == 'warning' for r in self.events))
        client.write_gatt_char.assert_not_awaited()

    async def test_reconnect_after_disconnect(self):
        device = SimpleNamespace(address='test', name='iConsole+0106')
        adv = SimpleNamespace(local_name='iConsole+0106')
        scanner = AsyncMock(return_value=[(device, adv)])
        calls = []
        def factory(*args, **kwargs):
            calls.append(args)
            return FakeClient()
        treadmill = self.treadmill(scanner=scanner, client_factory=factory)
        original_sleep = asyncio.sleep
        async def quick_sleep(delay):
            await original_sleep(0)
            if len(calls) >= 2:
                raise asyncio.CancelledError()
        with patch('pactobridge.ble.asyncio.sleep', side_effect=quick_sleep):
            with self.assertRaises(asyncio.CancelledError):
                await treadmill.run()
        self.assertEqual(len(calls), 2)
        self.assertTrue(any(r.get('state') == 'reconnecting' for r in self.events))

    async def test_subscription_timeout_cleans_up(self):
        client = FakeClient(notifications=False)
        async def hang(*args):
            await asyncio.sleep(60)
        client.start_notify.side_effect = hang
        with self.assertRaises(asyncio.TimeoutError):
            await self.treadmill(timeout=0.01).session(client)
        client.stop_notify.assert_awaited_once()
        client.write_gatt_char.assert_not_awaited()

    async def test_ambiguous_names_not_selected(self):
        device = SimpleNamespace(address='a', name='iConsole+0106')
        adv = SimpleNamespace(local_name='iConsole+0106')
        factory = AsyncMock()
        treadmill = self.treadmill(scanner=AsyncMock(return_value=[(device, adv), (device, adv)]), client_factory=factory)
        with patch('pactobridge.ble.asyncio.sleep', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await treadmill.run()
        factory.assert_not_called()
        self.assertTrue(any('Multiple matching' in r.get('message', '') for r in self.events))
