import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from pactobridge.recording import Recorder, read_events, replay
from pactobridge.cli import replay_capture
from pactobridge.uuids import FFF1, FFF2
from tests.test_protocols import status


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'capture.jsonl'

    def test_round_trip_flushed_and_no_overwrite(self):
        with Recorder(self.path) as recorder:
            recorder.event('notification', characteristic=FFF2, hex='01 ff')
            self.assertEqual(list(read_events(self.path))[0]['hex'], '01 ff')
            with self.assertRaises(FileExistsError):
                Recorder(self.path)
        output = []
        asyncio.run(replay(self.path, output.append, rate=0))
        self.assertEqual(len(output), 1)

    def test_corrupt_line_reports_location(self):
        self.path.write_text('{broken\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, ':1: invalid capture'):
            list(read_events(self.path))

    def test_invalid_timestamp_and_hex(self):
        for row in [dict(elapsed_s=-1), dict(elapsed_s=float('nan')),
                    dict(elapsed_s=True), dict(kind='notification', hex='GG', characteristic=FFF2)]:
            base = dict(schema=1, elapsed_s=0, kind='status')
            base.update(row)
            self.path.write_text(json.dumps(base) + '\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                list(read_events(self.path))

    def test_replay_candidates_explicit_and_offline(self):
        with Recorder(self.path) as recorder:
            recorder.event('notification', characteristic=FFF2, hex=status().hex())
        output = []
        asyncio.run(replay_capture(self.path, output.append, 'fitshow-v1-candidate', 0))
        self.assertEqual(output[-1]['candidate_kmh'], 8.0)
        self.assertFalse(output[-1]['verified'])
        self.assertNotIn('kmh', output[-1])

    def test_replay_rate_validation(self):
        for rate in [-1, float('inf'), float('nan')]:
            with self.assertRaises(ValueError):
                asyncio.run(replay(self.path, lambda row: None, rate))

    def test_replay_observed_fff1_notifications(self):
        with Recorder(self.path) as recorder:
            recorder.event('notification', characteristic=FFF1, hex=status().hex())
        output = []
        asyncio.run(replay_capture(self.path, output.append, 'fitshow-v1-candidate', 0))
        self.assertEqual(output[-1]['candidate_kmh'], 8.0)
        self.assertFalse(output[-1]['verified'])

    def test_replay_ignores_non_vendor_service(self):
        with Recorder(self.path) as recorder:
            recorder.event('notification', service='not-fff0',
                           characteristic=FFF1, hex=status().hex())
        output = []
        asyncio.run(replay_capture(self.path, output.append, 'fitshow-v1-candidate', 0))
        self.assertFalse(any(r['kind'] == 'candidate_speed' for r in output))
