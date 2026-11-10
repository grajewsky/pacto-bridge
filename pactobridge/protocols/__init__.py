"""Decoders are stateful per connection. Candidates are offline-only."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Speed:
    kmh: float


class Decoder(Protocol):
    name: str

    def feed(self, data: bytes) -> list[Speed]: ...
    def reset(self) -> None: ...


class RawDecoder:
    name = "raw"

    def feed(self, data: bytes) -> list[Speed]:
        return []

    def reset(self):
        pass


# Captured 219 B2 frames; console sequence 1/3/6/9 confirmed by the user.
# Import after Speed is defined to avoid a circular initialization dependency.
from .pacto import PactoDecoder

VERIFIED_DECODERS: dict[str, type] = {"pacto": PactoDecoder}


def decoder_for(name: str, *, live: bool = False) -> Decoder:
    if name == "raw":
        return RawDecoder()
    if name in VERIFIED_DECODERS:
        return VERIFIED_DECODERS[name]()
    if not live and name == "fitshow-v1-candidate":
        from .fitshow import FitShowCandidate
        return FitShowCandidate()
    raise ValueError(f"Decoder {name!r} has no verified Pacto live support")
