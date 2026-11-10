import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'protocol.dart';

const _ink = Color(0xff173a39);
const _teal = Color(0xff087f73);
const _canvas = Color(0xfff3f7f6);

class PactoApp extends StatelessWidget {
  const PactoApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'PactoBridge',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(seedColor: _teal),
          scaffoldBackgroundColor: _canvas,
          appBarTheme: const AppBarTheme(
            backgroundColor: _canvas,
            foregroundColor: _ink,
            surfaceTintColor: Colors.transparent,
            elevation: 0,
          ),
          cardTheme: CardTheme(
            color: Colors.white,
            surfaceTintColor: Colors.transparent,
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(22),
              side: const BorderSide(color: Color(0xffe5ecea)),
            ),
          ),
          filledButtonTheme: FilledButtonThemeData(
            style: FilledButton.styleFrom(
              backgroundColor: _teal,
              foregroundColor: Colors.white,
              minimumSize: const Size.fromHeight(52),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
            ),
          ),
          outlinedButtonTheme: OutlinedButtonThemeData(
            style: OutlinedButton.styleFrom(
              foregroundColor: _ink,
              minimumSize: const Size.fromHeight(48),
              side: const BorderSide(color: Color(0xffcbd9d6)),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
              textStyle: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
        ),
        home: const BridgePage(),
      );
}

class BridgePage extends StatefulWidget {
  const BridgePage({super.key});

  @override
  State<BridgePage> createState() => _BridgePageState();
}

class _BridgePageState extends State<BridgePage> with WidgetsBindingObserver {
  static const channel = MethodChannel('pl.pactobridge/ble');
  static const events = EventChannel('pl.pactobridge/events');

  Map<String, dynamic> capabilities = {};
  final devices = <String, Map<String, dynamic>>{};
  final logs = <String>[];
  StreamSubscription<dynamic>? subscription;
  Timer? replayTimer;
  double? speed;
  String state = 'Uruchamiam odbiornik Wi-Fi…';
  bool replay = false, busy = false;
  bool sessionActive = false, stoppedConfirmed = false, operatorPresent = false;
  String sessionState = 'INACTIVE';
  String transportState = 'INACTIVE';
  String? selectedAddress;

  bool get receiverReady =>
      ['RECEIVER_READY', 'WIFI_READY'].contains(transportState);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    subscription = events.receiveBroadcastStream().listen((dynamic raw) {
      final row = Map<String, dynamic>.from(raw as Map);
      if (!mounted) return;
      setState(() {
        if (row['kind'] == 'device') devices[row['address'] as String] = row;
        if (row['kind'] == 'speed' && !replay) {
          speed = (row['kmh'] as num).toDouble();
        }
        if (row['kind'] == 'unavailable' && !replay) speed = null;
        if (row['kind'] == 'session_state') {
          sessionState = row['state'] as String;
          sessionActive = !['INACTIVE', 'FAILED'].contains(sessionState);
        }
        if (row['kind'] == 'transport_state') {
          transportState = row['state'] as String;
        }
        if (row['message'] != null) {
          state = row['message'] as String;
          logs.insert(0, state);
          if (logs.length > 40) logs.removeLast();
        }
      });
    }, onError: (Object error) {
      if (mounted) setState(() => state = '$error');
    });

    // Start Wi-Fi discovery on launch; this never connects to or controls Pacto.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) call('prepareReceiver', {'transport': 'wifi'});
    });
  }

  Future<bool> call(String method, [Map<String, dynamic>? arguments]) async {
    if (busy) return false;
    setState(() => busy = true);
    try {
      final result = await channel.invokeMethod<dynamic>(method, arguments);
      if (mounted && result is Map) {
        setState(() => capabilities = Map<String, dynamic>.from(result));
      }
      return true;
    } on PlatformException catch (error) {
      if (mounted) setState(() => state = error.message ?? error.code);
      return false;
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> scan() async {
    setState(() {
      devices.clear();
      selectedAddress = null;
    });
    await call('scan');
  }

  Future<void> connectSession() async {
    final address = selectedAddress;
    if (address == null ||
        !stoppedConfirmed ||
        !operatorPresent ||
        !receiverReady) return;
    setState(() => sessionActive = true);
    final ok = await call('connectSession', {
      'address': address,
      'stopped': stoppedConfirmed,
      'operatorPresent': operatorPresent,
    });
    if (mounted) {
      setState(() {
        stoppedConfirmed = false;
        operatorPresent = false;
        if (!ok) sessionActive = false;
      });
    }
  }

  Future<void> demo() async {
    await call('stop');
    final rows =
        jsonDecode(await rootBundle.loadString('assets/workout.json')) as List;
    final decoder = PactoDecoder();
    final samples = <double>[];
    for (final row in rows) {
      samples.addAll(decoder.feed(parseHex(row['hex'] as String)));
    }
    if (!mounted || samples.isEmpty) return;
    setState(() {
      replay = true;
      speed = null;
      state = 'Nagranie demonstracyjne — nie jest wysyłane do Zwift.';
    });
    var index = 0;
    replayTimer?.cancel();
    replayTimer = Timer.periodic(const Duration(milliseconds: 120), (timer) {
      if (!mounted || index >= samples.length) {
        timer.cancel();
        if (mounted) {
          setState(() {
            replay = false;
            speed = null;
            state = 'Koniec demonstracji offline.';
          });
        }
      } else {
        setState(() => speed = samples[index++]);
      }
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState lifecycle) {
    if (lifecycle == AppLifecycleState.paused ||
        lifecycle == AppLifecycleState.detached) {
      replayTimer?.cancel();
      replay = false;
      speed = null;
    }
    if (lifecycle == AppLifecycleState.resumed && mounted) setState(() {});
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    replayTimer?.cancel();
    subscription?.cancel();
    super.dispose();
  }

  String get statusTitle {
    if (replay) return 'DEMO OFFLINE';
    switch (sessionState) {
      case 'RUNNING':
        return 'BIEŻNIA NADAJE';
      case 'START_REQUESTED':
        return 'OCZEKIWANIE NA RUCH';
      case 'READY':
        return 'BIEŻNIA GOTOWA';
      case 'STALE':
        return 'BRAK ŚWIEŻEJ TELEMETRII';
      case 'STOPPING':
        return 'ZATRZYMYWANIE';
      case 'FAILED':
        return 'SESJA ZAKOŃCZONA';
    }
    if (transportState == 'RECEIVER_READY') return 'ZWIFT POŁĄCZONY';
    if (transportState == 'WIFI_READY') return 'WI-FI GOTOWE';
    return busy ? 'ŁĄCZENIE…' : 'OCZEKUJE NA BIEŻNIĘ';
  }

  Color get statusColor {
    if (sessionState == 'RUNNING' || transportState == 'RECEIVER_READY') {
      return const Color(0xff087f73);
    }
    if (sessionState == 'STALE') return const Color(0xffb7791f);
    if (sessionState == 'FAILED') return const Color(0xffb5473e);
    return const Color(0xff617975);
  }

  Widget sectionTitle(String title, {String? caption}) => Padding(
        padding: const EdgeInsets.fromLTRB(2, 22, 2, 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Text(title,
                  style: const TextStyle(
                      color: _ink, fontSize: 19, fontWeight: FontWeight.w800)),
            ),
            if (caption != null)
              Text(caption,
                  style: const TextStyle(
                      color: Color(0xff718581),
                      fontSize: 12,
                      fontWeight: FontWeight.w600)),
          ],
        ),
      );

  Widget get speedCard => Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(22, 21, 22, 20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xff14534d), Color(0xff087f73)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(26),
          boxShadow: const [
            BoxShadow(
                color: Color(0x190c574f), blurRadius: 18, offset: Offset(0, 9)),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.speed_rounded, color: Colors.white70, size: 19),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text('PRĘDKOŚĆ BIEŻNI',
                      style: TextStyle(
                          color: Colors.white70,
                          fontSize: 12,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 1.1)),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                      color: Colors.white.withOpacity(.15),
                      borderRadius: BorderRadius.circular(30)),
                  child: Text(statusTitle,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 10,
                          fontWeight: FontWeight.w800,
                          letterSpacing: .5)),
                ),
              ],
            ),
            const SizedBox(height: 9),
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(speed?.toStringAsFixed(1) ?? '—',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 58,
                        height: 1.05,
                        fontWeight: FontWeight.w700,
                        letterSpacing: -2)),
                const SizedBox(width: 10),
                const Text('km/h',
                    style: TextStyle(
                        color: Colors.white70,
                        fontSize: 16,
                        fontWeight: FontWeight.w600)),
              ],
            ),
            const SizedBox(height: 7),
            Text(
              state,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white70, fontSize: 12.5),
            ),
          ],
        ),
      );

  Widget get connectionPath => Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
          child: Row(
            children: [
              const _PathNode(
                  icon: Icons.directions_run_rounded,
                  title: 'Pacto',
                  detail: 'BLE'),
              const Expanded(
                  child: Padding(
                padding: EdgeInsets.symmetric(horizontal: 8),
                child: Divider(color: Color(0xffc9d8d4)),
              )),
              Icon(Icons.arrow_forward_rounded,
                  color: statusColor, size: 19),
              const Expanded(
                  child: Padding(
                padding: EdgeInsets.symmetric(horizontal: 8),
                child: Divider(color: Color(0xffc9d8d4)),
              )),
              _PathNode(
                  icon: Icons.wifi_rounded,
                  title: 'Zwift',
                  detail: 'Wi-Fi',
                  active: receiverReady),
            ],
          ),
        ),
      );

  Widget get devicePicker {
    if (devices.isEmpty) {
      return Container(
        margin: const EdgeInsets.only(top: 12),
        padding: const EdgeInsets.all(15),
        decoration: BoxDecoration(
          color: const Color(0xfff4f8f7),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xffe2ece9)),
        ),
        child: const Row(
          children: [
            Icon(Icons.info_outline_rounded, color: _teal),
            SizedBox(width: 10),
            Expanded(
              child: Text('Włącz konsolę Pacto i wyszukaj bieżnię.',
                  style: TextStyle(color: Color(0xff586d69), fontSize: 13)),
            ),
          ],
        ),
      );
    }
    return Column(
      children: devices.values.map((device) {
        final address = device['address'] as String;
        final selected = selectedAddress == address;
        return Card(
          margin: const EdgeInsets.only(top: 10),
          color: selected ? const Color(0xffeef8f5) : Colors.white,
          child: RadioListTile<String>(
            value: address,
            groupValue: selectedAddress,
            onChanged: sessionActive
                ? null
                : (value) => setState(() => selectedAddress = value),
            activeColor: _teal,
            contentPadding: const EdgeInsets.symmetric(horizontal: 12),
            secondary: CircleAvatar(
              backgroundColor: selected
                  ? const Color(0xffd7eee8)
                  : const Color(0xffeff3f2),
              child: Icon(Icons.tune_rounded,
                  color: selected ? _teal : const Color(0xff718581)),
            ),
            title: Text(device['name'] as String,
                style: const TextStyle(
                    color: _ink, fontWeight: FontWeight.w700, fontSize: 14)),
            subtitle: Text(
                '$address  ·  ${device['rssi']} dBm',
                style: const TextStyle(fontSize: 11, color: Color(0xff718581))),
          ),
        );
      }).toList(),
    );
  }

  Widget get safetyCard => Card(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 15, 14, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.shield_outlined, color: _teal, size: 21),
                  SizedBox(width: 9),
                  Text('Przygotowanie na postoju',
                      style: TextStyle(
                          color: _ink,
                          fontSize: 15,
                          fontWeight: FontWeight.w800)),
                ],
              ),
              const SizedBox(height: 5),
              const Padding(
                padding: EdgeInsets.only(left: 30, bottom: 5),
                child: Text('Potrzebne przed każdym nowym połączeniem.',
                    style: TextStyle(
                        color: Color(0xff718581), fontSize: 12)),
              ),
              CheckboxListTile(
                value: stoppedConfirmed,
                onChanged: sessionActive
                    ? null
                    : (value) =>
                        setState(() => stoppedConfirmed = value ?? false),
                controlAffinity: ListTileControlAffinity.leading,
                contentPadding: EdgeInsets.zero,
                dense: true,
                visualDensity: VisualDensity.compact,
                activeColor: _teal,
                title: const Text('Pas stoi całkowicie; konsola pokazuje 0',
                    style: TextStyle(fontSize: 13, color: _ink)),
              ),
              CheckboxListTile(
                value: operatorPresent,
                onChanged: sessionActive
                    ? null
                    : (value) =>
                        setState(() => operatorPresent = value ?? false),
                controlAffinity: ListTileControlAffinity.leading,
                contentPadding: EdgeInsets.zero,
                dense: true,
                visualDensity: VisualDensity.compact,
                activeColor: _teal,
                title: const Text('Jestem przy bieżni i fizycznym STOP',
                    style: TextStyle(fontSize: 13, color: _ink)),
                subtitle: const Text('iConsole+ jest rozłączone',
                    style: TextStyle(fontSize: 11, color: Color(0xff718581))),
              ),
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: busy ||
                        replay ||
                        sessionActive ||
                        selectedAddress == null ||
                        !stoppedConfirmed ||
                        !operatorPresent ||
                        !receiverReady
                    ? null
                    : connectSession,
                icon: const Icon(Icons.link_rounded),
                label: const Text('Przygotuj sesję Pacto na postoju'),
              ),
              if (!receiverReady)
                const Padding(
                  padding: EdgeInsets.only(top: 9),
                  child: Text('Czekam na uruchomienie odbiornika Wi-Fi.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 11, color: Color(0xff718581))),
                ),
            ],
          ),
        ),
      );

  Widget get diagnostics => Card(
        clipBehavior: Clip.antiAlias,
        child: ExpansionTile(
          leading: const Icon(Icons.settings_outlined, color: _teal),
          title: const Text('Diagnostyka',
              style: TextStyle(color: _ink, fontWeight: FontWeight.w700)),
          subtitle: const Text('Uprawnienia i tryby zaawansowane',
              style: TextStyle(fontSize: 12)),
          childrenPadding: const EdgeInsets.fromLTRB(15, 0, 15, 14),
          children: [
            OutlinedButton.icon(
              onPressed: busy || replay || sessionActive
                  ? null
                  : () => call('permissions'),
              icon: const Icon(Icons.bluetooth_rounded),
              label: const Text('Sprawdź telefon i uprawnienia'),
            ),
            const SizedBox(height: 8),
            _capability('Bluetooth włączony', capabilities['enabled'] as bool?),
            _capability('Odbiornik BLE', capabilities['central'] as bool?),
            _capability(
                'Nadawanie BLE', capabilities['peripheral'] as bool?),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: busy ||
                      replay ||
                      sessionActive ||
                      transportState != 'INACTIVE'
                  ? null
                  : () => call('prepareReceiver', {'transport': 'ble'}),
              child: const Text('Odbiornik przez Bluetooth'),
            ),
            OutlinedButton(
              onPressed: busy ||
                      replay ||
                      sessionActive ||
                      transportState != 'INACTIVE'
                  ? null
                  : () => call('probeGatt'),
              child: const Text('Sprawdź serwer czujnika RSC'),
            ),
            OutlinedButton(
              onPressed: busy ||
                      replay ||
                      sessionActive ||
                      transportState != 'INACTIVE'
                  ? null
                  : () => call('probeRadio'),
              child: const Text('Test radia BLE · 60 s · bez prędkości'),
            ),
            OutlinedButton(
              onPressed: busy || replay || sessionActive ? null : demo,
              child: const Text('Demonstracja offline · bez Zwift'),
            ),
            if (logs.isNotEmpty) ...[
              const Divider(height: 25),
              Align(
                alignment: Alignment.centerLeft,
                child: Text('Ostatnie komunikaty',
                    style: Theme.of(context).textTheme.labelLarge),
              ),
              for (final message in logs.take(6))
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.chevron_right_rounded, size: 18),
                  title: Text(message,
                      style: const TextStyle(fontSize: 12), maxLines: 3),
                ),
            ],
          ],
        ),
      );

  Widget _capability(String label, bool? value) => ListTile(
        dense: true,
        visualDensity: VisualDensity.compact,
        contentPadding: EdgeInsets.zero,
        leading: Icon(
          value == true ? Icons.check_circle_outline : Icons.info_outline,
          color: value == true ? _teal : const Color(0xff879692),
        ),
        title: Text(label, style: const TextStyle(fontSize: 13)),
        trailing: Text(
          value == null ? '—' : value ? 'TAK' : 'NIE',
          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final receiverButtonEnabled =
        !busy && !replay && !sessionActive && transportState == 'INACTIVE';

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 18,
        title: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                  color: const Color(0xffdcefe9),
                  borderRadius: BorderRadius.circular(13)),
              child: const Icon(Icons.directions_run_rounded,
                  color: _teal, size: 23),
            ),
            const SizedBox(width: 11),
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('PactoBridge',
                    style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: _ink)),
                Text('Galaxy S22+  ·  Zwift',
                    style: TextStyle(
                        fontSize: 11,
                        color: Color(0xff718581),
                        fontWeight: FontWeight.w500)),
              ],
            ),
          ],
        ),
      ),
      body: SafeArea(
        top: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(18, 8, 18, 28),
          children: [
            speedCard,
            const SizedBox(height: 13),
            connectionPath,
            Row(
              children: [
                Expanded(
                  child: sectionTitle('Bieżnia', caption: 'ŹRÓDŁO BLE'),
                ),
                const SizedBox(width: 8),
                Padding(
                  padding: const EdgeInsets.only(top: 13),
                  child: OutlinedButton.icon(
                    onPressed:
                        busy || replay || sessionActive ? null : scan,
                    icon: const Icon(Icons.search_rounded, size: 18),
                    label: const Text('Szukaj iConsole+0106'),
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(0, 42),
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                    ),
                  ),
                ),
              ],
            ),
            devicePicker,
            sectionTitle('Bezpieczne połączenie', caption: 'POTWIERDŹ'),
            safetyCard,
            Card(
              child: Padding(
                padding: const EdgeInsets.all(15),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.info_outline_rounded,
                        color: _teal, size: 20),
                    const SizedBox(width: 11),
                    Expanded(
                      child: Text(
                        'START, zmiana prędkości i STOP obsługuj fizycznie na konsoli. Aplikacja nie steruje silnikiem. Zostaw ją otwartą podczas treningu.',
                        style: Theme.of(context)
                            .textTheme
                            .bodySmall
                            ?.copyWith(height: 1.45, color: _ink),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 10),
            diagnostics,
            const SizedBox(height: 9),
            TextButton.icon(
              onPressed: () {
                replayTimer?.cancel();
                setState(() {
                  replay = false;
                  speed = null;
                });
                call('stop');
              },
              icon: const Icon(Icons.link_off_rounded),
              label: const Text('Rozłącz most'),
              style: TextButton.styleFrom(foregroundColor: const Color(0xff8a4842)),
            ),
            if (!receiverReady)
              FilledButton.tonalIcon(
                onPressed: receiverButtonEnabled
                    ? () => call('prepareReceiver', {'transport': 'wifi'})
                    : null,
                icon: const Icon(Icons.wifi_rounded),
                label: const Text('Uruchom odbiornik Zwift Wi-Fi'),
              ),
          ],
        ),
      ),
    );
  }
}

class _PathNode extends StatelessWidget {
  const _PathNode(
      {required this.icon,
      required this.title,
      required this.detail,
      this.active = true});

  final IconData icon;
  final String title;
  final String detail;
  final bool active;

  @override
  Widget build(BuildContext context) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon,
              color: active ? _teal : const Color(0xff899a96), size: 22),
          const SizedBox(height: 3),
          Text(title,
              style: const TextStyle(
                  color: _ink, fontSize: 12, fontWeight: FontWeight.w800)),
          Text(detail,
              style: const TextStyle(
                  color: Color(0xff718581),
                  fontSize: 10,
                  fontWeight: FontWeight.w600)),
        ],
      );
}
