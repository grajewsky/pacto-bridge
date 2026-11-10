import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from .logging_config import configure


def capture_path():
    return Path("captures") / (datetime.now(timezone.utc).strftime("pacto-%Y%m%dT%H%M%S-%fZ") + ".jsonl")


def show(row):
    print(json.dumps(row), flush=True)


async def replay_capture(path, emit, decoder_name="raw", rate=1.0):
    from .protocols import decoder_for, VERIFIED_DECODERS
    from .recording import replay
    from .uuids import VENDOR_CHANNELS, VENDOR_SERVICE
    decoder = decoder_for(decoder_name)

    def receive(row):
        emit(row)
        if row["kind"] == "status" and row.get("state") in ("connecting", "disconnected", "reconnecting"):
            decoder.reset()
        if (row["kind"] == "notification"
                and row["characteristic"].lower() in VENDOR_CHANNELS
                and row.get("service", VENDOR_SERVICE).lower() == VENDOR_SERVICE):
            for sample in decoder.feed(bytes.fromhex(row["hex"])):
                verified = decoder.name in VERIFIED_DECODERS
                emit({"kind": "speed" if verified else "candidate_speed",
                      "kmh" if verified else "candidate_kmh": sample.kmh,
                      "verified": verified, "source": "offline replay", "decoder": decoder.name})
    await replay(path, receive, rate)


async def execute(args):
    if args.command == "scan":
        from .ble import discover
        for device, adv in await discover(args.timeout):
            show({"name": adv.local_name or device.name, "address": device.address,
                  "rssi": adv.rssi, "services": adv.service_uuids})
    elif args.command == "capture":
        from .app import capture
        path = args.output or capture_path()
        print(f"Recording to {path}. Ctrl+C stops. Decoder: {args.decoder}.", file=sys.stderr)
        job = capture(path, show, address=args.address, name=args.name,
                      polling=args.polling, decoder_name=args.decoder, advertise=args.advertise,
                      diagnostics=args.diagnose)
        if args.duration:
            try:
                await asyncio.wait_for(job, args.duration)
            except asyncio.TimeoutError:
                pass
        else:
            await job
    elif args.command == "replay":
        await replay_capture(args.path, show, args.decoder, args.rate)
    elif args.command == "import-hci":
        from .hci import import_hci
        show(import_hci(args.source, args.output, args.address,
                        notify_handle=args.notify_handle, write_handle=args.write_handle))


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def main():
    parser = argparse.ArgumentParser(description="PactoBridge — passive BLE capture and protocol analysis")
    parser.add_argument("--log", type=Path, default=Path("logs/pactobridge.jsonl"))
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Discover nearby BLE devices")
    scan.add_argument("--timeout", type=positive, default=10.0)
    live = sub.add_parser("capture", help="Live connection currently disabled pending console-control investigation")
    live.add_argument("--address", help="Windows address or macOS CoreBluetooth identifier")
    live.add_argument("--name", default="iConsole+0106")
    live.add_argument("--output", type=Path)
    live.add_argument("--duration", type=positive)
    live.add_argument("--polling", choices=["pacto-status"], help="Captured profile; live use is currently blocked")
    live.add_argument("--decoder", default="raw")
    live.add_argument("--advertise", action="store_true", help="Requires a verified live decoder")
    live.add_argument("--diagnose", action="store_true",
                      help="Read captured firmware/hardware fields and compare supported GATT write modes")
    offline = sub.add_parser("replay", help="Replay offline; never advertises")
    offline.add_argument("path", type=Path)
    offline.add_argument("--decoder", choices=["raw", "pacto", "fitshow-v1-candidate"], default="raw")
    offline.add_argument("--rate", type=float, default=1.0, help="Timing multiplier; 0 = immediate")
    hci = sub.add_parser("import-hci", help="Extract one peer's ATT traffic from BTSnoop/H4 offline")
    hci.add_argument("source", type=Path)
    hci.add_argument("--output", type=Path, required=True)
    hci.add_argument("--address", required=True, help="Peer address from this HCI capture")
    hci.add_argument("--notify-handle", type=lambda value: int(value, 0), required=True)
    hci.add_argument("--write-handle", type=lambda value: int(value, 0), required=True)
    sub.add_parser("gui", help="Open the optional PySide6 desktop app")
    args = parser.parse_args()
    try:
        configure(args.log)
        if args.command == "gui":
            from .gui import launch
            launch()
        else:
            asyncio.run(execute(args))
    except KeyboardInterrupt:
        pass
    except (ImportError, OSError, ValueError) as exc:
        parser.exit(1, f"PactoBridge: {exc}\n")
