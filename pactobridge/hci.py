"""Offline BTSnoop/H4 importer. Extract only one selected BLE peer's ATT data.

Original captures stay untouched. ATT value handles are explicit inputs, taken
from this connection's GATT discovery; never assume Android/Bleak handles match.
"""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import struct

from .uuids import FFF1, FFF2, VENDOR_SERVICE

BTSNOOP_UNIX_OFFSET = 0x00DCDDB30F2F8000


def records(path: Path):
    with path.open("rb") as stream:
        if stream.read(16) != b"btsnoop\0" + struct.pack(">II", 1, 1002):
            raise ValueError("Expected BTSnoop v1 with H4 link type 1002")
        while header := stream.read(24):
            if len(header) != 24:
                raise ValueError("Truncated BTSnoop record header")
            original, included, flags, dropped, stamp = struct.unpack(">IIIIQ", header)
            if included > original or included > 1_048_576:
                raise ValueError("Invalid BTSnoop record length")
            payload = stream.read(included)
            if len(payload) != included or included != original:
                raise ValueError("Truncated BTSnoop payload")
            yield stamp, flags, dropped, payload


@contextmanager
def new_output(path):
    stream = path.open("x", encoding="utf-8")
    try:
        with stream:
            yield stream
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def import_hci(source: Path, output: Path, address: str, *, notify_handle: int,
               write_handle: int):
    try:
        peer = bytes.fromhex(address.replace(":", ""))[::-1]
    except ValueError as exc:
        raise ValueError("Expected a six-byte Bluetooth address") from exc
    if len(peer) != 6 or notify_handle == write_handle or not all(
            1 <= h <= 65535 for h in (notify_handle, write_handle)):
        raise ValueError("Invalid peer address or ATT value handles")
    if source.resolve() == output.resolve():
        raise ValueError("Capture source and output must differ")
    output.parent.mkdir(parents=True, exist_ok=True)
    active = set()
    fragments = {}
    first = None
    last = None
    drops = 0
    elapsed = 0.0
    counts = {"notifications": 0, "writes": 0}
    with new_output(output) as target:
        def emit(kind, stamp, **fields):
            nonlocal elapsed
            # Android can timestamp concurrent RX/TX records out of order.
            # Preserve record order and exact source time; schedule replay on
            # a nondecreasing timeline without reordering ACL fragments.
            elapsed = max(elapsed, (stamp-first)/1e6)
            row = dict(fields, schema=1, kind=kind, elapsed_s=elapsed,
                       source_timestamp_us=stamp,
                       utc=datetime.fromtimestamp((stamp-BTSNOOP_UNIX_OFFSET)/1e6,
                                                  timezone.utc).isoformat())
            target.write(json.dumps(row) + "\n")

        for stamp, flags, dropped, packet in records(source):
            last = stamp
            if first is None:
                first = stamp
                emit("session", stamp, source="BTSnoop/H4 import", replay_only=True,
                     notify_value_handle=notify_handle, write_value_handle=write_handle)
            if dropped != drops:
                fragments.clear()
                emit("warning", stamp, message="HCI capture reports dropped packets")
                drops = dropped
            # LE Connection Complete / Enhanced Connection Complete.
            if (len(packet) >= 15 and packet[:2] == b"\x04\x3e"
                    and packet[3] in (1, 10) and packet[4] == 0):
                handle = int.from_bytes(packet[5:7], "little")
                active.discard(handle)
                fragments.pop((handle, 0), None)
                fragments.pop((handle, 1), None)
                if packet[9:15] == peer:
                    active.add(handle)
                    emit("status", stamp, state="connecting")
                continue
            if len(packet) >= 7 and packet[:2] == b"\x04\x05":
                handle = int.from_bytes(packet[4:6], "little")
                if handle in active:
                    active.remove(handle)
                    emit("status", stamp, state="disconnected")
                fragments.pop((handle, 0), None)
                fragments.pop((handle, 1), None)
                continue
            if len(packet) < 5 or packet[0] != 2:
                continue
            handle_flags, size = struct.unpack_from("<HH", packet, 1)
            handle, boundary = handle_flags & 0xFFF, handle_flags >> 12 & 3
            if handle not in active:
                continue
            if len(packet) != size + 5:
                raise ValueError("Invalid HCI ACL packet length")
            key = handle, flags & 1
            if boundary in (0, 2):
                fragments[key] = bytearray(packet[5:])
            elif boundary == 1 and key in fragments:
                fragments[key].extend(packet[5:])
            else:
                continue
            frame = fragments[key]
            if len(frame) < 4:
                continue
            length, cid = struct.unpack_from("<HH", frame)
            if len(frame) < length + 4:
                continue
            fragments.pop(key)
            if len(frame) != length + 4:
                raise ValueError("Invalid reassembled L2CAP length")
            if cid != 4 or length < 3:
                continue
            opcode = frame[4]
            attribute = int.from_bytes(frame[5:7], "little")
            if flags & 1 and opcode in (0x1B, 0x1D) and attribute == notify_handle:
                kind, characteristic = "notification", FFF1
                counts["notifications"] += 1
            elif not flags & 1 and opcode in (0x12, 0x52) and attribute == write_handle:
                kind, characteristic = "write", FFF2
                counts["writes"] += 1
            else:
                continue
            emit(kind, stamp, service=VENDOR_SERVICE, characteristic=characteristic,
                 hex=bytes(frame[7:]).hex(" "), att_opcode=opcode)
        if first is None:
            raise ValueError("BTSnoop file contains no records")
        emit("session_end", last, incomplete_fragments=len(fragments))
    return counts
