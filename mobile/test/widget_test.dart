import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:pacto_bridge/bridge_app.dart';
void main() {
  testWidgets('Opening network discovery never connects the treadmill or supplies speed', (tester) async {
    const channel = MethodChannel('pl.pactobridge/ble');
    final calls = <String>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call.method);
      expect(call.arguments, {'transport': 'wifi'});
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, null));
    tester.view.physicalSize = const Size(1080, 3000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const PactoApp());
    await tester.pumpAndSettle();
    expect(calls, ['prepareReceiver']);
    expect(find.text('PactoBridge'), findsOneWidget);
    expect(find.textContaining('START, zmiana prędkości'), findsOneWidget);
    final button = tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Przygotuj sesję Pacto na postoju'));
    expect(button.onPressed, isNull);
  });
}
