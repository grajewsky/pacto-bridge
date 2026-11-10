# ZIPRO Pacto protocol evidence — 2026-11-09

> **Current hardware interlock:** The user reports that physical START and speed buttons became unresponsive during the nRF Connect test. Live connections are now disabled in PactoBridge, including passive capture and diagnostics, while the cause is investigated. Captured command semantics do not establish freedom from console side effects. Offline replay remains available. Do not run the historical live-test commands below until normal console operation is restored and connection effects are understood.

## Verified observations

The OPPO LogKit export finally contains a full H4 BTSnoop stream:
`BT_HCI_2026_1109_165559.cfa` (1,417,058 bytes). The original remains under
`captures/android/oppo-logkit/`. Its peer connection was identified by the
address seen in the earlier Pacto scanner capture, not by coincidental handles.
Only that connection's vendor ATT traffic is extracted into
`captures/pacto-iconsole-20261109.jsonl`; unrelated phone traffic is excluded.

The extraction has 223 vendor writes and 228 vendor notifications. All 451
protocol messages satisfy `checksum = sum(all preceding frame bytes) mod 256`.
There are 216 occurrences of the status query and 219 B2 telemetry frames;
some telemetry is unsolicited. The user confirmed that the console showed
1, then 3, 6 and 9 during this capture, matching decoded plateaus. Zero appears
in standby frames. This verifies the console-reported speed interpretation;
independent physical belt velocity has not been measured.

| Item | Observed value |
| --- | --- |
| Advertised name | iConsole+0106 |
| Vendor service | FFF0 |
| Notify characteristic | FFF1, ATT value handle 0x0012 in Android capture |
| Write characteristic | FFF2, ATT value handle 0x0010 in Android capture |
| CCCD | ATT handle 0x0013, value 01 00 |
| Identification request / expected reply | F0 A0 01 00 91 / F0 B0 01 D3 74 |
| Status request | F0 A2 01 D3 66, write without response |
| Full telemetry prefix / length | F0 B2 01 D3 / 19 bytes |
| Speed in km/h | `((byte[12]-1)*100 + byte[13]-1) / 10` |
| Checksum | Last byte, additive modulo 256 |

Indices above are zero-based. The offset-by-one representation uses base-100
speed digits; neither speed byte may be zero, and the low digit must be 1..100.
Frames with different device bytes, message type, length, invalid fields or
checksum do not produce measurements. Frame reconstruction supports split and
coalesced notification values and resets on reconnect. A status/error code is
never used to invent zero speed.

The independently written implementation is corroborated by the
[QZ TRX App Gate treadmill driver](https://github.com/cagnulein/qdomyos-zwift/blob/master/src/devices/trxappgateusbtreadmill/trxappgateusbtreadmill.cpp):
it polls this exact A2 message for a matching dialect and uses the same
base-100, offset-by-one speed fields. This is corroboration after identifying
matching traffic on the Pacto, not compatibility inferred from device naming.
No upstream implementation is copied into this repository.

## Enabled operations

`--decoder pacto` enables this captured telemetry dialect. `--polling pacto-status`
opts into the captured A0 identification exchange, followed by a read-only
status request once per second (slower than the app's approximately 0.5-second cadence).
The exact B0 reply, including checksum and model bytes, must arrive before any
status polls are sent. Missing or mismatched replies fail the session; fragment
reassembly and identification state reset on each connection. Polling requires the exact device name
and observed FFF1-notify/FFF2-write layout, and uses only the source-reviewed
identification and status requests listed above. The default remains passive with no protocol writes.

The app capture also includes another A0 message at the end of the session,
plus A3, A4, A5 and AF traffic. Those additional messages remain excluded from
the allowlist. In particular A5 includes start/stop
operations in the reference driver; blindly copying the app's complete startup
sequence could operate the motor. No start, stop, speed, incline, workout/user
setup or DFU commands are exposed.

## Direct status-only test and identification fix

The user-run capture `pacto-20261109T161311-854352Z.jsonl` has one initial
connection timeout, followed by successful GATT discovery and notification
subscription. It contains 43 A2 requests and zero notifications. Consequently,
status-only polling did not establish telemetry in this run.

The official-app trace starts with exactly `F0 A0 01 00 91`, answered by
`F0 B0 01 D3 74` about 83 ms later, before any A3/A4/A5/AF messages. The
[original iConsole reverse engineering](https://github.com/haraldh/iconsole/blob/master/iConsole.py)
identifies the A0/B0 family as ping/pong; its bike telemetry layout is different
and is not used here. The trace confirms these exact bytes on this Pacto.
The profile now performs only this identification exchange before A2 polling,
and refuses to proceed without the matching reply. This exchange does not
include a motor command. Its ability to establish direct telemetry on a fresh
connection is **still pending hardware validation**. No other startup frames
are sent as a fallback.

## Identification test: no replies; inspect direct HCI transport next

The subsequent user-run capture `pacto-20261109T162100-948802Z.jsonl` records
three attempts to subscribe and send the captured identification request, with
zero notifications. Two attempts reached the identification timeout; the third
was cancelled by the 90-second session deadline. No A2 polls were sent, as
required by the identification gate. An awaited BLE write returning without an
exception does not establish that the expected ATT bytes reached the treadmill.

Before changing more protocol messages, collect a controller-level trace with
`bash scripts/capture_direct_ble.sh` in the ordinary WSL terminal. The helper
runs btmon on hci0 with sudo for at most 105 seconds and runs the current
non-control PactoBridge profile as the normal user for 90 seconds. It saves the
raw HCI trace, decoded btmon text, application log and notification capture in a
new `captures/direct-*` directory. The test does not require a moving belt.
The script passes bash syntax checking; hardware execution is pending because
the agent sandbox cannot access Bluetooth monitor sockets.

This BlueZ monitor capture can use a different BTSnoop link type from the
Android H4 capture; use the accompanying btmon text or `btmon --read` to analyze
it. The H4-only importer should not be used on a different link type.

## Direct controller trace and connection setup timing

The first controller trace in `captures/direct-20261109T174015-xfakBu/` confirms
CCCD handle 0x0013 written with 01 00 and acknowledged, followed by the exact
captured A0 bytes on ATT value handle 0x0010 using Write Command (0x52). No
notification was returned. Thus the trace does not support a wrong write handle,
wrong command bytes or wrong notification descriptor as the current cause.

The same trace contains an early connection failure (controller reason 0x3e)
and treadmill advertisement RSSI between -89 and -80 dBm, median -81 dBm. After
retries/discovery, the final identification starts only 2.68 seconds before the
45-second application deadline stops notifications. The helper now captures
90 seconds of application traffic within a 105-second controller recording.

There is a measurable setup timing difference: the official app waits 1.007
seconds after the CCCD write response before A0, whereas the direct client sends
A0 about 4 ms after the response. The profile now waits 1 second after
`start_notify` returns, using the captured timing as a conservative setup delay.
It still sends exactly the same identification and status bytes, with no new
control or initialization commands. No evidence yet proves timing is the cause;
validate with a stopped/power-cycled treadmill, phone Bluetooth off and the PC
adapter close to the treadmill to reduce connection instability.

The first diagnostic run succeeded in saving the actual HCI trace. The updated
helper and one-second delay are pending hardware execution. See
`pacto-controller-test-2026-11-09.json` for the measured findings.

## Full-duration WSL follow-up and native Windows comparison

The follow-up `captures/direct-20261109T174719-zVejZQ/` contains three captured
A0 writes and zero notifications, despite the one-second setup delay. Two
attempts wait the full identification timeout; the third reaches the session
deadline. This does not confirm setup timing as the solution. No additional
protocol initialization or control messages are enabled.

The connected USB controller is CSR8510 A10, VID:PID 0a12:0001, attached to WSL
through USB/IP. The user identified its Windows BUSID as 1-7. A native Python
3.12 installation is available. The next comparison uses the same PactoBridge
code/profile via Windows WinRT rather than Linux/BlueZ. This tests a host-stack
variable without guessing more protocol commands; it does not establish that
WSL or this controller is the cause.

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_windows_ble.ps1 -BusId 1-7`

Run in Windows PowerShell. The helper first verifies that the specified BUSID
maps uniquely to 0a12:0001, then detaches only that adapter from WSL. Windows
cannot use an adapter while it is forwarded to WSL, as described by
[Microsoft](https://learn.microsoft.com/en-us/windows/wsl/connect-usb). The helper
records a Windows Bluetooth inventory, creates a separate `.venv-win`, installs
the project and captures the existing profile for 90 seconds. Results go into a
unique `captures/windows-*` directory. It does not reattach the adapter to WSL,
modify global Bluetooth settings or add treadmill protocol commands.

Native execution is pending. PowerShell is unavailable in the agent sandbox;
the helper has been reviewed statically, with a syntax-parser check added to
Windows CI. The script stops if the selected BUSID belongs to another device.

## Native Windows result and bounded diagnostics

`captures/windows-20261109T185614-fc3d8432/` confirms that the native WinRT
baseline also receives zero notifications. It connects and subscribes, then
sends the exact A0 packet with the captured delay. The failure is therefore not
specific to Linux/BlueZ; this does not yet distinguish adapter behavior from
additional device setup requirements.

The successful Android trace performs two ordinary GATT reads after CCCD
subscription and before A0: firmware revision 2A26 (value `05`) followed by
hardware revision 2A27 (value `C0.00.C0.00`), both under Device Information 180A.
Those were absent in the PC baselines. Diagnostic mode now reads and records
exactly these two characteristics when advertised as readable. It never reads
DFU or substitutes other characteristics if either field is missing.

`capture --decoder pacto --polling pacto-status --diagnose` keeps the normal
profile unchanged, but in the diagnostic session reads these fields, sends the
same captured A0 packet without response, and waits the configured reply timeout.
If no identification arrives, it repeats the exact same A0 bytes with GATT
response enabled, only when the characteristic advertises both write modes.
No alternative magic bytes or motor commands are introduced. Each attempt logs
backend write completion separately from receiving the exact B0 reply; backend
completion alone is not evidence of protocol identification. If identified,
A2 polling uses the successful write mode. If neither identifies, the diagnostic
session ends rather than repeating both probes indefinitely. Initial connection
failures may retry within the outer session deadline. Delayed replies are visible
in the raw log; a reply during the second mode does not by itself prove which
attempt caused it.

The Windows helper accepts `-Diagnose`, with a default outer limit of 180 seconds
for that mode. The adapter is already available to Windows after the baseline;
omit `-BusId` to leave its current assignment unchanged. The normal GUI/profile
continues using the original write mode and does not automatically run probes.
The two metadata reads and mode comparison are pending physical validation.

## Windows diagnostics result: revision reads and both write modes

`captures/windows-20261109T190540-2ad83a99/` confirms firmware `05` and hardware
`C0.00.C0.00`, matching the working Android trace. Both Write Command and Write
Request complete successfully at the Bleak backend. Each still times out
waiting for identification; zero notifications and zero A2 polls are recorded.
Thus neither ordinary Device Information reads nor selecting the other GATT
write mode established the protocol in this run. No additional control frames
are enabled from this result.

The working Android HCI stream was also checked for target-link SMP/encryption
before A0. None was found; an encryption command belongs to another connection,
so it is not evidence for introducing pairing as another Pacto requirement.

The next discriminating test is the captured minimal exchange in nRF Connect
on the same Android phone, with iConsole+ and PactoBridge disconnected. Enable
FFF1 notifications under FFF0, read 2A26 then 2A27 under 180A, then write exactly
`F0 A0 01 00 91` to FFF2 in byte-array/hex format using Write Without Response.
Record whether FFF1 returns `F0 B0 01 D3 74`, and export the actual nRF log.
No DFU, A3/A4/A5/AF, target speed or start/stop operations are part of this test.
If the phone succeeds, focus on the PC-side connection path; that alone would
not identify a particular adapter fault. If it does not succeed, compare its
actual startup/timing with the successful official-app trace before adding
more requirements. The diagnostic helper remains available, but repeating the
unchanged PC tests is not the next evidence step.

Tool references: [nRF Connect for Mobile](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile)
and [official Android client/log documentation](https://github.com/nordicsemi/Android-nRF-Connect/blob/main/documentation/README.md).

## Independent Android identification confirmed by the user

The user confirms that nRF Connect returns `F0 B0 01 D3 74` after sending the
captured `F0 A0 01 00 91` request. A raw nRF log has not yet been supplied, so
this is recorded as user confirmation rather than an imported packet fixture.
It establishes that the identification message can work outside iConsole+ on
this phone. PC-side transport/connection differences remain to investigate;
this alone does not prove that the CSR adapter is defective or needs a patch.
No generic driver/firmware changes are justified by a matching USB VID/PID alone.

The next minimal phone operation is the already captured read-only A2 status
request `F0 A2 01 D3 66` on FFF2, with FFF1 notifications left enabled. A B2
response would verify that the read-only A0/A2 subset works on the phone without
A3/A4/A5/AF workout/control messages. Preserve the returned frame or nRF log.
No additional byte variants are enabled in the PC application based only on
the identification result.

## Independent Android status response: screenshot evidence

The user's nRF Connect screenshot shows FFF2 set to the captured A2 status
query, FFF1 notifications enabled and this 19-byte response:
`F0 B2 01 D3 01 01 01 01 01 01 01 01 01 01 01 01 01 02 85`.
The additive checksum is 85 and the existing decoder returns 0.0 km/h.
The screenshot explicitly shows connected / not bonded, consistent with the
absence of target-link encryption/SMP in the earlier successful HCI capture.
This is evidence that the minimal read-only exchange works outside iConsole+
on this phone. It does not establish physical motion or solve the PC-side
connection issue. The PC adapter/driver/connection setup cause remains unknown;
no hardware fault or need to buy a replacement has been proven.

## Physical console controls: new report supersedes read-only assumptions

The user clarified that physical START and speed buttons would not work during
the independent phone test. The causative step has not been isolated. The A0
exchange might enter an app-control session, or the connection/subscription
itself might affect the console. Successful telemetry parsing does not resolve
this behavior. Earlier uses of “read-only” for the full A0/A2 session are
therefore premature; this is a reassessment of initialization safety, not a
change to the observed speed-byte interpretation.

Public live entry points are blocked before BLE activity, and GUI live controls
are disabled. Captured profiles are preserved as offline protocol evidence.
The immediate requirement is to restore and confirm physical operation with
nRF Connect disconnected and phone Bluetooth off; restart with the belt
stopped if needed. No guessed unlock, A5 motor action or extra initialization
frame is enabled as a workaround. Device operation without BLE and the effect
of each connection step must be understood before re-enabling a live bridge.

## Control requirements confirmed after recovery

The user confirms physical control was restored after disconnect/restart, asks
for application control as well as physical controls, and confirms that all
physical buttons work after starting a workout with the original iConsole+.
This is the target coexistence behavior. The manufacturer Pacto manual also
describes app takeover after Bluetooth connection (PDF page 11), though the
current hosted revision names FitShow rather than this iConsole firmware.
That manual is context for console behavior, not proof of byte compatibility.

The raw trace was checked for all target writes: 223 go to FFF2, and one enables
its notification descriptor. The only repeated command is A2. No speed-setting
request varies during the user-confirmed 1/3/6/9 sequence, so physical control
or device-side behavior remains consistent with the data; a speed-control
opcode must not be guessed. An operator-marked app/physical START, speed and
moving-belt STOP recording is required to establish those operations and
session prerequisites. See [the single-session collection plan](control-capture.md)
and `pacto-control-requirements.json`. No motor commands or automatic physical
key forwarding are enabled until verified. A phone-assisted BLE transport is
being evaluated because that phone's minimal exchange works; changing the
transport alone does not implement the required control session.

## Connection precondition: stopped belt (operator report)

The user reports that iConsole+ cannot connect when a workout is already
started and speed is nonzero. Future operator-led connection checks must start
with a completely stopped belt and zero displayed speed, connect and initialize,
then start only through an explicit operator action. The exact failure stage
(BLE link versus application session) has not been isolated. A BLE link alone
does not establish that the vendor session is ready.

The earlier native Windows script said the treadmill could remain stopped, but
did not require or record that state. Consequently its zero-notification results
cannot distinguish this prerequisite from other connection causes. Do not
reinterpret them as proof that the belt was moving or that the PC adapter failed.
Reconnection while running also remains unverified. No automatic STOP, motor
start, resumed speed target or live-interlock change follows from this report.

## Capture import and repeatability

`python -m pactobridge import-hci SOURCE.cfa --address PEER_ADDRESS --notify-handle 0x12 --write-handle 0x10 --output captures/imported.jsonl`

The importer accepts BTSnoop v1 / H4 (link type 1002), follows the selected peer's
LE connection handles and disconnects, reconstructs ACL/L2CAP fragments and
extracts only that peer's configured ATT value handles. Handles come from the
capture's GATT enumeration; live communication uses discovered characteristic
objects. Output is replay-only. Existing files are not overwritten, invalid
imports remove their partial output, and original captures remain untouched.
One Android timestamp regresses by about 2.06 seconds in this stream. Source
timestamps and UTC are retained, while replay elapsed time is made nondecreasing
without reordering ACL fragments.

Regression fixtures contain five actual B2 frames (0/1/3/6/9) with device
identifiers omitted. Validation also replays all 219 captured telemetry frames
through the decoder and RSC encoder. Decoder tests reject corrupt checksums,
control replies, other device bytes and invalid speed fields; transport tests
verify the status-only write and refusal on other device names/layouts.

## Zwift validation remaining

`--advertise` can now use the verified `pacto` decoder and only its fresh live
readings. Offline replay never starts the peripheral transport. Unknown speed
is not zero; disconnect invalidates readings and stale data stops advertising.
The mandatory RSC cadence field remains zero as an unavailable placeholder.

Actual Bless advertising, peripheral stop/restart, adapter support for central
and peripheral roles together, native Windows/macOS operation and Zwift pairing
still need hardware validation. Console speed matches do not establish those
transport capabilities or physical belt calibration.

## Physical speed changes and stop capture ? native phone collection

New LogKit session `2026-11-09_20-22-42@bluetooth` was started through the phone UI and saved locally after the user reported the belt stopped. Packet files and a manifest are in `captures/android/controls-2026-11-09_20-22-42@bluetooth-d8154dd0/`. Screen recording stayed off; no treadmill motor controls were clicked by the agent.

The main H4 file `BT_HCI_2026_1109_202058.cfa` starts during an existing workout. Cached controller connection metadata maps connection handle 3 to the previously recorded treadmill address. The main file has no connection-complete event or GATT discovery; attribution uses that cached mapping plus matching vendor telemetry, with this limitation explicit in `analysis.json`. It was not passed through the standard importer by inventing a connection event. Extracted vendor rows are in `vendor-candidate-rows.json` and are marked as candidate analysis, not an independently discovered live GATT profile.

There are 296 vendor messages, all with valid additive checksums: 150 B2 telemetry notifications, 141 A2 polls, two B5/03 notifications, one closing A0 request (`f0 a0 01 d3 64`), one B0 reply and one BF/03 notification. Speed starts at 2.7 km/h, decreases through 2.6/2.5/2.4/2.3/2.2/2.1 to 2.0, then decelerates to 0.0 around 71.72 seconds after capture start. These are console-reported values, not independently measured belt velocity.

The operator was asked to change physical speed and use physical STOP, then reported stopped. Exact key timestamps and explicit confirmation of each key action were not supplied. No A5 motor request or speed-setting write appears in this recording, so it is consistent with device-side physical control without app command forwarding during this already initialized session. B5/03 cannot yet be assigned a definitive key-event meaning. The recording does not establish app STOP payloads, app speed-setting payloads, startup prerequisites, or how to reproduce the complete session. The live interlock remains enabled.

## Stopped-state original-app connection recorded through UI

The agent started a second Bluetooth LogKit recording after the operator confirmed the belt stopped, closed the previous workout summary, navigated the original app tutorial/device picker and selected `iConsole+0106`. The UI reported `Connected successfully`. QUICK START was not selected and no motor action was clicked. The session was saved to `captures/android/controls-2026-11-09_20-28-55@bluetooth-26df2b58/` (main H4 file 376,191 bytes).

Unlike the previous mid-session capture, the main stream includes a successful LE connection-complete event for the known treadmill peer (controller handle 4). The existing importer extracted 33 vendor writes and 33 notifications to `pacto-startup.jsonl`. The ATT value handles 0x12/0x10 were supplied from earlier discovery, not newly derived from this session's GATT discovery. All vendor checksums validate. Offline replay decoded all 31 B2 frames at 0.0 km/h.

Observed sequence relative to recording start:

- 117.292 s: peer connection completes.
- 120.162 s: app writes `f0 a0 01 d3 64`; B0 reply at 120.183 s.
- 120.664 s: app writes `f0 a5 01 d3 04 6d` while stopped; B5/05 reply at 120.755 s.
- 121.162 s onward: 31 A2 polls at about 0.5-second intervals, each answered by stopped B2 telemetry.
- 137.374 s: peer disconnect event. The exact cause of disconnection is not established by this analysis.

This newly observed connection uses D3 in A0, whereas the first official-app capture began with `f0 a0 01 00 91`. The D3 form also occurred at the end of older sessions. It is therefore no longer accurate to describe it solely as a closing command. Both forms have observed B0 responses on Android. This is evidence of a variant, not a reason to silently add fallback probes or change the current captured profile. A5/04 is still only observed while already stopped; moving-belt app STOP and its effect on physical-button readiness remain unverified. No A3/A4/AF workout setup appears in this stopped connection. The live interlock stays enabled.

## Full connection/workout/physical-stop recording

The Bluetooth recording remained active across the user's physical STOP of an earlier workout and a new QUICK START. After the user confirmed zero, the agent saved the previous workout summary (cancelled the discard dialog), closed an advertisement, and left the app at Home. The user was instructed to choose QUICK START and start at 1 km/h, then reported running. The agent observed 1.0 km/h in the app. Tapping the blank workout area displayed `Please control your movement through your console.` No app speed or STOP controls were exposed there. The user was then instructed to change to 2 km/h physically, wait about 10 seconds, and press physical STOP, and reported stopped. Individual user taps and their exact times were not recorded, so app-only versus physical START is not established.

Saved session: `captures/android/controls-2026-11-09_20-39-51@bluetooth-f9b8363e/`; main H4 file 1,526,790 bytes. The standard importer follows the new known-peer connection within this file, excluding the already-active initial connection rather than inventing its identity. Output: `pacto-workout.jsonl` (192 writes, 206 notifications, all vendor checksums valid). Prior ATT handles 0x12/0x10 were supplied, not newly discovered. `analysis.json` preserves the event sequence, operator context and limitations.

Relative to recording start:

- 169.012 s: new peer connection.
- 171.906 s: A0/D3 -> B0; 172.406 s: A5/04 -> B5/05 in stopped state.
- 174.909 s: captured A3 -> B3; 175.408 s: A4 -> B4; 175.909 s: AF/02 -> BF/02. Payloads match the earlier full-session capture.
- 179.986 s: unsolicited B5/02 from treadmill.
- 183.919 s: app A5/02; B5/03 follows at 184.000 s. First nonzero B2 is 0.2 km/h at 184.572 s, reaching 1.0 at 186.074 s.
- 242.295 to 246.177 s: speed rises from 1.1 through intermediate values to 2.0 km/h. No speed-setting write occurs.
- 264.177 s: another unsolicited B5/03; 265.047 s: app A0/D3 -> B0. No A5/04 or other motor STOP write occurs around physical STOP.
- 269.092 s: B2 reports 0.0 km/h; BF/03 and disconnect follow at 269.171/269.174 s.

Offline CLI replay succeeds and returns the captured acceleration/deceleration values. The message sequence corroborates physical control during a complete official-app session. It does not prove that A3/A4/AF enable physical controls, that B5/02 must always trigger A5/02, or that a standalone app START is supported. Never automatically forward a guessed key event. App-based speed and moving STOP remain unobserved; the original app explicitly directs this workout to console controls. The live interlock stays enabled pending a source-reviewed session/control design and hardware validation. No changes to the live command allowlist were made.

## S22+ hardware: physical START is self-contained (2026-11-10)

Evidence: captures/android/pacto-1794300630032-d1d69abb-final.jsonl shows user
physical START -> B5/02 at221775ms -> first moving B2 at226449ms, with ZERO
A5/02 writes. Physical console starts its own countdown/motor. B5/02 must not
be treated as a mandatory request for an app motor command.

Mobile implementation now has no motor START API/write. After acknowledged,
zero-gated initialization, it observes actual movement in READY/START_REQUESTED
and transitions RUNNING. Nonzero during initialization still rejects setup.
A countdown without movement returns READY; STOP is still physical, observed via
B5/03 then B2 zero. No speed-setting or moving STOP command was introduced.

Successful physical-only trial: pacto-1794301790970-e90a1d75-final.jsonl and
s22plus-live-rsc-20261110T091229467760Z.json. Source287 samples, max2.0km/h;
PC received621 RSC notifications, max1.996875km/h (RSC quantization), final0.
States READY -> START_REQUESTED -> RUNNING -> STOPPING -> ENDED -> INACTIVE.
No A5/02. Operator physically selected1, then2, thenSTOP and confirmed stopped.
Summary: captures/android/s22plus-moving-bridge-validation.json. Actual Zwift
pairing is separate from this independently verified GATT transfer.
