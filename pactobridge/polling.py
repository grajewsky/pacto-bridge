"""Captured protocol facts. Live use is blocked pending console behavior checks."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PollingProfile:
    evidence: str
    requests: tuple[bytes, ...]
    interval_s: float = 2.0
    response: bool = True
    device_name: str | None = None
    identify_request: bytes | None = None
    identify_response: bytes | None = None
    notify_settle_s: float = 0.0


# A captured exchange is not proof of freedom from console side effects. There is no
# CLI/GUI arbitrary-hex write facility and no imported user polling config.
CAPTURED_PROFILES: dict[str, PollingProfile] = {
    "pacto-status": PollingProfile(
        evidence="docs/pacto-protocol.md: captured A0/B0 identification and 216 A2 status polls",
        requests=(bytes.fromhex("f0 a2 01 d3 66"),),
        interval_s=1.0, response=False, device_name="iConsole+0106",
        identify_request=bytes.fromhex("f0 a0 01 00 91"),
        identify_response=bytes.fromhex("f0 b0 01 d3 74"),
        notify_settle_s=1.0),
}


def get_profile(name: str | None) -> PollingProfile | None:
    if name is None:
        return None
    if name not in CAPTURED_PROFILES:
        raise ValueError(f"Polling profile {name!r} is not a captured Pacto profile")
    profile = CAPTURED_PROFILES[name]
    if not profile.evidence or not profile.requests or profile.interval_s < 1:
        raise ValueError("Incomplete polling verification")
    if (profile.identify_request is None) != (profile.identify_response is None):
        raise ValueError("Identification requires a request and expected reply")
    return profile
