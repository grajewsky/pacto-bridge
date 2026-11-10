List<int> parseHex(String value) => value.trim().split(RegExp(r'\s+'))
    .map((s) => int.parse(s, radix: 16)).toList();

/// Captured Pacto B2 dialect; control/status frames never invent a speed.
class PactoDecoder {
  final List<int> _buffer = [];
  void reset() => _buffer.clear();
  List<double> feed(List<int> data) {
    _buffer.addAll(data);
    final result = <double>[];
    while (_buffer.length >= 19) {
      final f = _buffer.take(19).toList();
      final valid = f[0] == 0xf0 && f[1] == 0xb2 && f[2] == 1 && f[3] == 0xd3 &&
          f.take(18).fold<int>(0, (a, b) => a + b) % 256 == f[18] &&
          f.sublist(4, 18).every((b) => b > 0) &&
          f[12] >= 1 && f[12] <= 100 && f[13] >= 1 && f[13] <= 100;
      if (valid) {
        result.add(((f[12] - 1) * 100 + f[13] - 1) / 10);
        _buffer.removeRange(0, 19);
      } else { _buffer.removeAt(0); }
    }
    return result;
  }
}
