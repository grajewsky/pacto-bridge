# One-phone network output

S22+ receives Pacto over BLE and publishes RSC over the local network. No second
phone is required. Android NSD advertises `_wahoo-fitness-tnp._tcp` and TCP36866.
The app uses its own persistent virtual sensor identity; no NIC or Bluetooth name
is changed. TXT includes serial-number, mac-address and the RSC service UUID.

This independently written implementation follows public protocol facts in
[the unofficial WFTNP description](https://github.com/elfrances/wahoo-fitness-tnp).
[QZ's treadmill integration](https://github.com/cagnulein/qdomyos-zwift/blob/master/src/virtualdevices/virtualtreadmill.cpp)
corroborates using this transport for running. No implementation code was copied.

Messages have a six-byte header, network-order lengths/UUIDs and BLE-order RSC
values. Discovery, characteristic reads and notification subscriptions are
supported. All characteristic writes are rejected. No network input reaches a
Pacto write or motor command. Requests are bounded to4096 bytes and four peers.

Prepare the network server and stopped Pacto session before selecting the running
sensor in Zwift. Zwift's network client has a10s inactivity timeout; the server
stays available for reconnection while waiting for genuine source measurements.
There are no synthetic zero or keepalive speed samples. Once real telemetry
begins, absence for3s closes the publisher, advertisement and sockets. Background
also closes BLE/network. Offline replay cannot supply network measurements.

Tests cover framing/fragmentation, bounds, service/profile responses, subscriptions,
write rejection, original RSC encoding, no invented samples and stale/reset handling.
The one-phone WiFi route was hardware-validated end to end on 2026-11-10. A PC
subscriber received 231 actual RSC frames at 0.998 km/h and a second 106-frame
capture showed changing speed from 2.095 to 6.005 km/h. Zwift assigned the virtual
sensor as Run Speed with status ready; the operator confirmed the speed displayed
correctly in game. The earlier621-frame moving test covered BLE output.

Optional read-only PC diagnostics: install the `network` project extra, then run
`scripts/probe_android_wifi.py --interface <LAN_IP>`. Add `--subscribe --duration90`
(with a space before90) to record actual measurements after source preparation.
