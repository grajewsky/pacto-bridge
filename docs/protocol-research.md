# Protocol research — 2026-11-09

> **Current hardware interlock:** The user reports that physical START and speed buttons became unresponsive during the nRF Connect test. Live connections are now disabled in PactoBridge, including passive capture and diagnostics, while the cause is investigated. Captured command semantics do not establish freedom from console side effects. Offline replay remains available. Do not run the historical live-test commands below until normal console operation is restored and connection effects are understood.

> Historical investigation notes. The later full LogKit capture and user-confirmed speed sequence establish the Pacto dialect; see [current protocol evidence](pacto-protocol.md). Statements below describe evidence available at each earlier stage.

## Evidence boundary

The user's initial description reports iConsole+0106 and FFF0/FFF1/FFF2, with no notifications after subscription. The user-run capture `pacto-20261109T145811-181293Z.jsonl` now confirms GATT enumeration: FFF1 is notify at handle 17; FFF2 is write/write-without-response at handle 15. These roles reverse the initial description. Four connection attempts failed before subscription because the program required notify on FFF2; no telemetry was captured. This run does not establish a need for a handshake. The program now selects the notification characteristic by discovered properties under FFF0. No Pacto telemetry packet capture, vendor protocol specification tied to this firmware, handshake, checksum or speed offset is verified. No reviewed source establishes ZIPRO Pacto compatibility. FFF0 is a vendor UUID, not a protocol identifier.

## Follow-up hardware test

Capture `pacto-20261109T150835-801142Z.jsonl` confirms successful subscription to FFF1 after selecting by GATT properties. The application listened for approximately 76.5 seconds, received zero notifications, recorded zero connection errors and attempted zero protocol writes. The session completed normally. The initial channel-selection bug is resolved; this run supports investigating app initialization/polling but does not prove which messages, if any, are required. Actual speed decoding remains unavailable. Further passive repetition alone is unlikely to identify a silent request/response protocol; obtain a successful official-app trace before enabling any writes.

## Android official-app report

The OPPO report collected at 16:41:32 contains a Bluetooth stack log confirming a connection to iConsole+0106, FFF2 write value handle 0x0010, FFF1 notify value handle 0x0012 and CCCD handle 0x0013. Unlike Bleak's exposed handles in the earlier log, these are explicitly ATT value handles; prefer discovered characteristic objects rather than hardcoded handle numbers. The app enables notifications, then repeatedly writes to the vendor channel at roughly 0.5-second intervals, with notification events following. This is evidence of request/response activity, not verification that any specific request is read-only.

The ZIP has eight .cfa files, each containing only the 16-byte BTSnoop header, and no full BTSnoop payload or embedded BTSnooz section was located. The stack log identifies the active raw capture as `/data/misc/bluetooth/cached_hci/btsnoop_hci_20261109_163631.cfa`, which is not included in the ZIP. An ordinary ADB pull is the next collection step; its accessibility is unverified. No command bytes, speed decoder or polling profile are enabled from metadata alone. See `android-report-2026-11-09.json` for the machine-readable findings.

## Primary sources reviewed

- [ZIPRO iConsole connection instructions](https://www.zipro.pl/cms/iconsole.pdf): manufacturer app-pairing guidance, not a byte protocol. The [Pacto manual](https://www.zipro.pl/cms/manuals/PACTO.pdf) is another manufacturer reference; model revisions must be checked against the physical console.
- [FitSHOW treadmill protocol v1.1, 2017](https://fitshow.com/download/运动秀电跑蓝牙通讯协议.pdf): `02 CMD DATA FCS 03`, XOR of command/data, little-endian multibyte values, speed in tenths. Device information is command 50, status 51. A full status response includes status, current speed/incline, time, distance, calories, steps, heart rate and program segment. The candidate decoder supports only the 17-byte full status shape for states 1/3/4/10. It ignores short state responses and control acknowledgments. These are FitSHOW facts, not Pacto facts.
- [QZ FitShow implementation](https://github.com/cagnulein/qdomyos-zwift/blob/master/src/devices/fitshowtreadmill/fitshowtreadmill.cpp) and [header](https://github.com/cagnulein/qdomyos-zwift/blob/master/src/devices/fitshowtreadmill/fitshowtreadmill.h): demonstrate initialization variants, information requests, telemetry and control in one driver. They also expose configurable units/dialects. Importing an entire startup sequence could send control commands, so none is copied into the application.
- [tyge68/fitshow-treadmill](https://github.com/tyge68/fitshow-treadmill): open-source project targeting Sportstech F31, a useful comparison target; its support claim does not extend to Pacto.
- [QZ iConcept bike driver](https://github.com/cagnulein/qdomyos-zwift/blob/master/src/devices/iconceptbike/iconceptbike.cpp): uses RFCOMM serial and 55-prefixed frames with model-specific initialization. This is a different transport/equipment family; similarly named iConcept/iConsole equipment is insufficient evidence for reuse. [QZ Toorx treadmill driver](https://github.com/cagnulein/qdomyos-zwift/blob/master/src/devices/toorxtreadmill/toorxtreadmill.cpp) also illustrates serial-service discovery rather than proving a match to this GATT layout.
- [Nordic RSCS reference](https://nrfconnectdocs.nordicsemi.com/ncs/latest/nrf/doxygen/html/structbt__rscs__measurement_a87ae0e05a8a824a1a853d27854945a66.html): instantaneous speed has 256 units per metre/second. [Bluetooth SIG assigned numbers](https://www.bluetooth.com/specifications/assigned-numbers/) identify standard service/characteristic numbers.
- [Bleak](https://bleak.readthedocs.io/en/latest/) is a GATT client; [Bless server example](https://github.com/kevincar/bless/blob/master/examples/server.py) provides the peripheral API used by the optional adapter. Neither establishes Zwift interoperability on this adapter.

The candidate implementation is independently written from protocol facts in the vendor document. No upstream driver implementation is vendored. URLs refer to moving upstream branches; hardware verification should pin the exact source revision and preserve the underlying captures.

## Commands remain disabled

FitSHOW documents information and status queries, but their meaning on the Pacto is unknown. A command that is read-only in one protocol may have a different meaning in another. FitSHOW control-ready may start the treadmill in compatibility modes, so a guessed initialization sequence is especially inappropriate. The program has no arbitrary hex-write UI or CLI and no active profiles.

`polling.py` supplies the extension point for reviewed read-only requests. `protocols.VERIFIED_DECODERS` supplies the live decoder registry. Both were empty before the full LogKit capture. The current registries now include `pacto` and the read-only `pacto-status` profile; see current evidence above. They are source-code integration points for engineering review, not user configuration toggles.

## Verification required before enabling a profile

1. Capture the official app's initial connection and notification enable, preserving raw request and response direction, handles/UUIDs and timing. Do not replay unknown commands to discover their effect.
2. Correlate multiple console speed plateaus and transitions with response bytes. Confirm km/h versus mph and whether the reported value is actual reported speed or a target echo. Separate speed from cadence and steps.
3. Establish frame length, fragmentation, checksum, units, stop/pause/error states and reconnect behavior. Retain raw evidence even if no decoder matches.
4. Independently review each initialization/poll request as read-only for this exact model/firmware. Omit identity writes, time writes, control-ready, start/stop, target speed, incline and DFU operations.
5. Add anonymized capture fixtures, reference console readings and regression tests before registering a decoder/profile. Reset decoder state across reconnects; invalid data must never refresh speed freshness.
6. Validate a second device can read the advertised RSC service and decode known real treadmill readings; then pair under Zwift's running speed source and compare its displayed speed. Test no-data, disconnect and peripheral restart on native Windows and macOS.

If the official app requires unsafe control initialization merely to read speed, keep that path disabled and report the limitation; consider external belt-speed sensing separately if needed.
