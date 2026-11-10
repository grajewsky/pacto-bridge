import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:pacto_bridge/protocol.dart';
void main() {
  test('196 real workout frames preserve acceleration and physical stop', () {
    final rows = jsonDecode(File('assets/workout.json').readAsStringSync()) as List;
    final decoder = PactoDecoder(); final speeds = <double>[];
    for (final row in rows) {
      final data = parseHex(row['hex'] as String);
      speeds.addAll(decoder.feed(data.sublist(0, 7)));
      speeds.addAll(decoder.feed(data.sublist(7)));
    }
    expect(speeds.length, 196); expect(speeds.first, 0); expect(speeds.last, 0);
    expect(speeds.toSet(), containsAll([0.2, 0.5, 0.7, 1.0, 2.0]));
  });
  test('bad checksum and controls cannot invent zero', () {
    final decoder = PactoDecoder();
    final f = parseHex('f0 b2 01 d3 01 01 01 01 01 01 01 01 01 01 01 01 01 02 85');
    f[18] = 0;
    expect(decoder.feed(f), isEmpty);
    expect(decoder.feed(parseHex('f0 b5 01 d3 03 7c')), isEmpty);
    decoder.reset(); expect(decoder.feed(f.sublist(10)), isEmpty);
  });
}
