# PactoBridge

PactoBridge sends live speed from a ZIPRO Pacto treadmill to Zwift using one
Android phone. The phone reads the treadmill over Bluetooth LE, then publishes a
standard Running Speed and Cadence (RSC) sensor over Wi-Fi. Zwift on the Windows
PC discovers it as **PactoBridge WiFi**.

```text
ZIPRO Pacto  ── Bluetooth LE ──>  Android / Galaxy S22+
                                      │
                                      └── Wi-Fi / WFTNP ──> Zwift (Run Speed)
```

The one-phone route was validated with a Samsung Galaxy S22+ (SM-S906B, Android
16) and Zwift for Windows. No second phone or Zwift Companion app is required.

## Quick start

1. Connect the phone and the Windows PC to the same local Wi-Fi network.
2. Open PactoBridge on the phone and leave it in the foreground. The Wi-Fi sensor
   starts automatically.
3. Wake the treadmill console with its physical **STOP** button. Confirm the belt
   is completely stopped, the console reads zero, and iConsole+ is disconnected.
4. In PactoBridge, scan for and select **iConsole+0106**, check both operator
   confirmations, then tap **Przygotuj sesję Pacto na postoju**. Wait for the live
   zero-speed reading and the ready state.
5. In Zwift choose **Run → Speed Source → PactoBridge WiFi** (the network/Wi-Fi
   sensor icon).
6. Use the physical treadmill console for **START**, speed changes, and **STOP**.

Zwift can drop an idle network sensor after about 10 seconds. Prepare Pacto before
selecting the sensor in Zwift. If the phone app goes into the background, its BLE
and Wi-Fi connections close.

## Safety and scope

- The app does not send motor **START**, speed, incline, or **STOP** commands.
- Session setup reads device information and sends only the captured initialization
  protocol required to begin reading telemetry while the belt is stopped.
- Only actual live treadmill measurements are sent to Zwift. There are no generated
  speeds or network motor controls.
- Disconnecting PactoBridge does **not** stop the treadmill. Use the physical STOP.
- Keep the operator beside the console during use.

## Build for Android

Requirements: Flutter 3.19 or later, Android SDK 34, Java 17, and an ARM64 Android
device running Android 12 or later. From PowerShell at the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_android.ps1
```

The script analyzes Flutter code, runs Flutter and Kotlin tests, then builds the
ARM64 APK at `mobile/dist/PactoBridge-S22Plus-validation.apk`. This validation APK
is signed with a local debug key; it is not a Play Store release. The app source is
in `mobile/`.

For a manual Flutter analysis:

```powershell
cd mobile
flutter pub get
flutter analyze
```

## Troubleshooting

**The treadmill does not appear:** wake the console with physical STOP, check that
Bluetooth is enabled, disconnect iConsole+, and scan again from PactoBridge.

**Zwift does not show PactoBridge WiFi:** check that both devices are on the same
Wi-Fi/LAN, reopen PactoBridge, wait for its Wi-Fi-ready status, then refresh Zwift's
Run speed sources.

**Telemetry pauses:** the independent Wi-Fi sender repeats the last received speed
every 250 ms until a new real reading arrives. The app displays the measurement age.
During a gap, Zwift can therefore continue showing the previous speed even if the
belt has changed speed. A real BLE disconnect or session stop ends transmission and
clears the retained value; a new session must receive a real measurement first.

## Project layout

- `mobile/` — Flutter UI and Android/Kotlin BLE, WFTNP and RSC implementation.
- `mobile/README.md` — detailed phone setup and operation.
- `mobile/SESSION_WORKFLOW.md` — operator session steps and hardware validation.
- `mobile/NETWORK_PROTOCOL.md` — Wi-Fi sensor protocol notes.
- `scripts/build_android.ps1` — Android build and validation script.
- `pactobridge/` — earlier Python protocol research and desktop tooling; not needed
  to run the Android bridge.

Local device logs and captures are intentionally excluded from this repository.
No software license has been selected yet.
