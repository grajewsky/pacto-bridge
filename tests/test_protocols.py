import math
import struct
import unittest
from functools import reduce
from operator import xor
from pactobridge.protocols import decoder_for
from pactobridge.protocols.fitshow import FitShowCandidate
from pactobridge.polling import get_profile
from pactobridge.sensor import encode_rsc, RunningSensor


def status(speed=80, state=3):
    payload = bytes([0x51, state, speed, 0]) + bytes(10)
    return b'\x02' + payload + bytes([reduce(xor, payload, 0), 3])


class ProtocolTests(unittest.TestCase):
    def test_raw_never_invents_speed(self):
        self.assertEqual(decoder_for('raw', live=True).feed(status()), [])

    def test_unverified_candidate_blocked_live(self):
        with self.assertRaises(ValueError):
            decoder_for('fitshow-v1-candidate', live=True)
        with self.assertRaises(ValueError):
            RunningSensor('fitshow-v1-candidate')
        with self.assertRaises(ValueError):
            RunningSensor('raw')

    def test_unverified_polling_blocked(self):
        self.assertIsNone(get_profile(None))
        with self.assertRaises(ValueError):
            get_profile('fitshow')

    def test_candidate_fragments_and_coalescing(self):
        decoder = FitShowCandidate()
        self.assertEqual(decoder.feed(status()[:8]), [])
        samples = decoder.feed(status()[8:] + status(60))
        self.assertEqual([s.kmh for s in samples], [8.0, 6.0])

    def test_internal_delimiters_and_deceleration(self):
        samples = FitShowCandidate().feed(status(3, state=4))
        self.assertEqual([s.kmh for s in samples], [0.3])

    def test_corruption_noise_and_short_data(self):
        frame = bytearray(status())
        frame[-2] ^= 1
        decoder = FitShowCandidate()
        self.assertEqual(decoder.feed(b'noise' + frame + b'\x02\x51\x03'), [])
        self.assertEqual([s.kmh for s in decoder.feed(status())], [8.0])

    def test_no_target_echo_or_unknown_state(self):
        for cmd, state in [(0x53, 3), (0x51, 99)]:
            frame = bytearray(status(state=state))
            frame[1] = cmd
            frame[-2] = reduce(xor, frame[1:-2], 0)
            self.assertEqual(FitShowCandidate().feed(frame), [])

    def test_reset_discards_old_connection_fragment(self):
        decoder = FitShowCandidate()
        decoder.feed(status()[:8])
        decoder.reset()
        self.assertEqual(decoder.feed(status()[8:]), [])

    def test_long_noise_bounded(self):
        decoder = FitShowCandidate()
        decoder.feed(bytes(10000))
        self.assertLess(len(decoder.buffer), 17)

    def test_rsc_known_units_and_zero(self):
        self.assertEqual(encode_rsc(3.6), b'\x00\x00\x01\x00')
        self.assertEqual(encode_rsc(0), bytes(4))
        flags, raw, cadence = struct.unpack('<BHB', encode_rsc(10))
        self.assertLessEqual(abs(raw / 256 * 3.6 - 10), 3.6 / 512)
        self.assertEqual((flags, cadence), (0, 0))

    def test_rsc_rejects_invalid(self):
        for speed in [-1, math.nan, math.inf, 1000]:
            with self.subTest(speed=speed), self.assertRaises(ValueError):
                encode_rsc(speed)
