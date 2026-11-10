from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pactobridge.app import capture
from pactobridge.ble import Treadmill
from pactobridge.cli import replay_capture
from pactobridge.recording import Recorder
from pactobridge.uuids import FFF1


class LiveInterlockTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_capture_modes_block_before_creating_files_or_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'blocked.jsonl'
            for options in ({}, {'decoder_name': 'pacto', 'polling': 'pacto-status'},
                            {'decoder_name': 'pacto', 'polling': 'pacto-status', 'diagnostics': True},
                            {'decoder_name': 'pacto', 'polling': 'pacto-status', 'advertise': True}):
                with self.subTest(options=options), patch('pactobridge.app.Treadmill') as central, \
                     patch('pactobridge.app.RunningSensor') as sensor:
                    with self.assertRaisesRegex(ValueError, 'physical START/speed buttons'):
                        await capture(output, Mock(), **options)
                    central.assert_not_called()
                    sensor.assert_not_called()
                    self.assertFalse(output.exists())

    async def test_direct_central_run_cannot_bypass_capture_guard(self):
        scanner = AsyncMock()
        factory = Mock()
        treadmill = Treadmill(Mock(), Mock(), scanner=scanner, client_factory=factory)
        with self.assertRaisesRegex(ValueError, 'Live treadmill connections are disabled'):
            await treadmill.run()
        scanner.assert_not_awaited()
        factory.assert_not_called()

    async def test_offline_replay_still_reads_real_captured_telemetry(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/pacto-status.json').read_text())['samples'][2]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'offline.jsonl'
            with Recorder(source) as recorder:
                recorder.event('notification', characteristic=FFF1, hex=fixture['hex'])
            events = []
            await replay_capture(source, events.append, 'pacto', 0)
            speeds = [r for r in events if r['kind'] == 'speed']
            self.assertEqual([r['kmh'] for r in speeds], [fixture['kmh']])
            self.assertEqual(speeds[0]['source'], 'offline replay')
