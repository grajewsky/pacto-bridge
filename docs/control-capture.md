# Verification of application and physical controls

The user requests app START/STOP/speed controls plus retained physical controls,
and confirms that all physical buttons work after starting a workout with the
original iConsole+ app. This is the behavior to reproduce. It supersedes any
assumption that physical buttons necessarily remain unusable throughout a full
app session. The incomplete A0/A2 test did affect physical operation.

## What remains to capture

The original stream contains 223 writes to FFF2 and one CCCD write. Of those,
216 are identical A2 status polls. No varying speed-setting request appears.
An A5/02 request is followed by running telemetry; an A5/04 appears while
initially stopped, which does not verify stopping a moving belt. An unsolicited
B5/02 precedes the app's start message; its operator meaning is not yet marked.
No physical event is automatically forwarded as a motor command on that basis.

Record one normal iConsole+ workout using OPPO LogKit's Bluetooth category:

1. Close nRF Connect and PactoBridge. Use the normal console controls to stop
   the belt completely and finish the current workout. Confirm the belt is
   stationary and displayed speed is zero. Start LogKit recording as before.
2. Connect using iConsole+ while the belt remains stopped. Note connection and
   workout-start times separately. Only after the app is ready, start a workout
   from the app at a low, comfortable speed.
3. If the app offers speed control, change speed through the app at two or
   three low values, for example 1, 2 and 3 km/h. Note the order. If there is
   no speed control in iConsole+, report that instead of trying other controls.
4. Change speed once using the physical buttons, then stop using physical STOP.
5. If normal operation permits, start using physical START, then stop from the app.
6. Note which operations worked and approximate times; stop and save LogKit to local/USB storage.

Use the official app's normal operation and the treadmill's normal safety
procedures. No raw motor commands are sent by this project during collection.
This recording should establish session prerequisites, actual control payloads,
moving-belt STOP behavior, and physical-button feedback/priority.

The user reports that the original app cannot connect to a workout already
running at nonzero speed. Treat a stationary belt as a connection precondition.
It is not yet known whether that rejection occurs at BLE connection or vendor
session initialization. Earlier PC failures did not record belt state, so this
is a possible explanation to check, not a proven cause. Do not initiate a motor
STOP command just to establish the precondition. Reconnection during motion is
also unverified; it must not silently restore a session or an old speed target.

## Copy only Bluetooth packet files

Connect the phone over USB and run from Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\pull_oppo_bluetooth.ps1
```

The helper uses the inspected ADB installation and requires one authorized
device (or an explicit `-Serial`). It selects the most recent timestamped
Bluetooth session under the already verified LogKit export directory and
copies only CFA/partial-CFA packet files under bthci and cached_hci. It preserves
the remote directory structure in a new `captures/android/controls-*` folder
and creates a manifest; old captures and phone files remain untouched.
The displayed session timestamp must match the new test. No root or protected
`/data` reads are used. A PowerShell syntax-parser check is configured in CI;
local execution is pending because PowerShell is unavailable in the sandbox.

## Implementation constraints after verification

Application commands must correspond to an explicit operator action. Connection
and reconnection must never start the motor or restore an old speed target.
Live measured/reported speed is separate from the requested speed. Physical
changes must not be overwritten by periodically resending an app target, and
the meaning of physical STOP feedback must be verified before implementing it.
An uncertain state, missing acknowledgment or disconnect must invalidate
control readiness rather than invent a state or replay an action.

The live interlock stays enabled while the full control-session behavior is
verified. The captured byte checksums and decoder are not themselves evidence
that motor control or console coexistence is ready.
