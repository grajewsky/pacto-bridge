"""Pacto 01/D3 status dialect, verified against the user's HCI capture.

Only B2 telemetry yields speed. Control echoes and state codes never synthesize
speed. See docs/pacto-protocol.md for capture evidence and remaining limits.
"""
from . import Speed


class PactoDecoder:
    name = "pacto"
    PREFIX = bytes.fromhex("f0 b2 01 d3")
    SIZE = 19

    def __init__(self):
        self.buffer = bytearray()

    def reset(self):
        self.buffer.clear()

    def feed(self, data: bytes) -> list[Speed]:
        self.buffer.extend(data)
        samples = []
        while len(self.buffer) >= self.SIZE:
            frame = self.buffer[:self.SIZE]
            if (frame[:4] == self.PREFIX and sum(frame[:-1]) % 256 == frame[-1]
                    and all(frame[4:18]) and 1 <= frame[12] <= 100
                    and 1 <= frame[13] <= 100):
                tenths = (frame[12] - 1) * 100 + frame[13] - 1
                samples.append(Speed(tenths / 10))
                del self.buffer[:self.SIZE]
            else:
                del self.buffer[0]
        return samples
