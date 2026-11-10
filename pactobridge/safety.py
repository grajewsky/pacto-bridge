"""Current hardware interlock, based on the user's console-control report."""

LIVE_CONNECTION_BLOCK_REASON = (
    "Live treadmill connections are disabled: physical START/speed buttons "
    "were unavailable in the minimal BLE test. Normal controls have been "
    "restored and work in a full iConsole+ session, but that control session "
    "is not yet verified in PactoBridge. "
    "Offline replay remains available."
)


def require_live_connection():
    # Deliberately no CLI override. Captured bytes and valid checksums do not
    # establish that entering an app session preserves physical controls.
    raise ValueError(LIVE_CONNECTION_BLOCK_REASON)
