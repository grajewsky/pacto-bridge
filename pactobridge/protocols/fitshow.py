"""Offline FitSHOW v1.1 candidate, independently implemented from vendor PDF.

Only the 17-byte full status response is accepted. Other dialects are unknown.
The protocol has no length byte: restrict to this known response shape, rather
than splitting at 0x03, which may also occur inside the payload or checksum.
"""
from functools import reduce
from operator import xor

from . import Speed


class FitShowCandidate:
    name = "fitshow-v1-candidate"
    FRAME_SIZE = 17

    def __init__(self):
        self.buffer = bytearray()

    def reset(self):
        self.buffer.clear()

    def feed(self, data: bytes) -> list[Speed]:
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= self.FRAME_SIZE:
            frame = self.buffer[:self.FRAME_SIZE]
            if (frame[:2] == b"\x02\x51" and frame[2] in (1, 3, 4, 10)
                    and frame[-1] == 3
                    and reduce(xor, frame[1:-2], 0) == frame[-2]):
                # Raw current-speed byte, including deceleration. Do not infer
                # zero from a state code or decode control-target echoes.
                result.append(Speed(frame[3] / 10.0))
                del self.buffer[:self.FRAME_SIZE]
            else:
                del self.buffer[0]
        return result
