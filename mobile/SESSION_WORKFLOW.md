# PactoBridge: ZIPRO Pacto → Galaxy S22+ → Zwift

## Validated one-phone route

The S22+ reads live Pacto measurements over BLE and publishes standard Running
Speed and Cadence over local WiFi using Wahoo Direct Connect/WFTNP. Zwift on the
same LAN selects `PactoBridge WiFi` as Run Speed. No second phone or Companion app
is required. End-to-end moving speed was hardware-validated on 2026-11-10; the
operator confirmed the displayed speed in Zwift.

## Operating steps

1. Connect the S22+ and Zwift PC to the same local WiFi network. Open PactoBridge
   and leave it in the foreground. It starts the WFTNP receiver automatically.
2. Wake the Pacto console with its physical STOP button. Make sure the belt is fully
   stopped and iConsole+ is disconnected. In the app, scan for and select
   `iConsole+0106`, check both stopped/operator boxes, and tap **Prepare Pacto
   session**. Wait for the real zero-speed reading and READY state.
3. In Zwift choose RUN and select `PactoBridge WiFi` (network/WiFi icon) as the
   speed source. Prepare the Pacto source before choosing it; Zwift expires an
   idle WFTNP connection after 10 seconds.
4. Use the physical treadmill console for START, speed changes, and STOP. The app
   sends no motor START, speed-setting, or STOP command. Disconnecting the bridge
   does not stop the belt. Keep PactoBridge foregrounded; backgrounding ends BLE
   and WiFi.

## Evidence

- The native Pacto session reached READY, received physical-console start status,
  and delivered real B2-derived speeds from 1.0 to 6.0 km/h.
- A Windows WFTNP subscriber received 231 RSC frames at 0.998 km/h and a second
  capture of 106 frames with changing speed from 2.095 to 6.005 km/h.
- Zwift logs show `PactoBridge WiFi` assigned as Run Speed and `status=ready`;
  the operator confirmed the speed displayed correctly in Zwift.
- Captures are under `../captures/android/s22plus-wifi-20261110T120308416965Z.json`
  and `../captures/android/s22plus-wifi-20261110T120537984543Z.json`. The matching
  native session journal is `pacto-1794312095794-374fe263.jsonl` in Android app
  storage.

The validation APK is ARM64 and locally debug-signed; it is not a Play Store release.
Build and device details are in `dist/build-report.json`. The network implementation
and diagnostic command are documented in [NETWORK_PROTOCOL.md](NETWORK_PROTOCOL.md).
