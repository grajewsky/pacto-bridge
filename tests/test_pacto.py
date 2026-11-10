import json
from pathlib import Path
import unittest
from pactobridge.protocols import decoder_for
from pactobridge.protocols.pacto import PactoDecoder
from pactobridge.polling import get_profile

SAMPLES = json.loads((Path(__file__).parent / 'fixtures/pacto-status.json').read_text())['samples']


class PactoTests(unittest.TestCase):
    def test_real_console_correlated_capture_frames(self):
        decoder = decoder_for('pacto', live=True)
        for sample in SAMPLES:
            self.assertEqual([s.kmh for s in decoder.feed(bytes.fromhex(sample['hex']))], [sample['kmh']])

    def test_fragmented_coalesced_noise_and_reconnect(self):
        frame = bytes.fromhex(SAMPLES[2]['hex'])
        decoder = PactoDecoder()
        self.assertEqual(decoder.feed(b'noise' + frame[:12]), [])
        self.assertEqual([s.kmh for s in decoder.feed(frame[12:] + frame)], [3,3])
        decoder.feed(frame[:8])
        decoder.reset()
        self.assertEqual(decoder.feed(frame[8:]), [])

    def test_corrupt_checksum_wrong_device_and_control_echo(self):
        for index in [0,1,2,3,18]:
            frame = bytearray.fromhex(SAMPLES[2]['hex'])
            frame[index] ^= 1
            if index != 18:
                frame[-1] = sum(frame[:-1]) & 255
            self.assertEqual(PactoDecoder().feed(frame), [])

    def test_invalid_speed_digits_not_negative_or_synthetic_zero(self):
        for high, low in [(0,1),(1,0),(1,101),(101,1)]:
            frame=bytearray.fromhex(SAMPLES[2]['hex'])
            frame[12:14]=bytes([high,low])
            frame[-1]=sum(frame[:-1]) & 255
            self.assertEqual(PactoDecoder().feed(frame), [])

    def test_base100_speed_above_ten(self):
        frame=bytearray.fromhex(SAMPLES[2]['hex'])
        frame[12:14]=bytes([2,21])  # 100 + 20 tenths, no cadence involved.
        frame[-1]=sum(frame[:-1]) & 255
        self.assertEqual(PactoDecoder().feed(frame)[0].kmh, 12)

    def test_polling_allowlist_is_only_observed_status_query(self):
        profile=get_profile('pacto-status')
        self.assertEqual(profile.requests,(bytes.fromhex('f0 a2 01 d3 66'),))
        self.assertFalse(profile.response)
        self.assertGreaterEqual(profile.interval_s,1)
        self.assertEqual(profile.device_name,'iConsole+0106')
        self.assertEqual(profile.identify_request, bytes.fromhex('f0 a0 01 00 91'))
        self.assertEqual(profile.identify_response, bytes.fromhex('f0 b0 01 d3 74'))
        for request in (profile.identify_request, *profile.requests):
            self.assertEqual(sum(request[:-1]) & 255, request[-1])
