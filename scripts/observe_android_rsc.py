"""Validate actual live Android RSC output. No treadmill connection or control writes."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import time

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

SERVICE = '00001814-0000-1000-8000-00805f9b34fb'
MEASUREMENT = '00002a53-0000-1000-8000-00805f9b34fb'
FEATURE = '00002a54-0000-1000-8000-00805f9b34fb'
IDENTITY_SERVICE = '9260b200-2460-4ce3-956a-f1a3d6e086f1'
IDENTITY_VALUE = '9260b201-2460-4ce3-956a-f1a3d6e086f1'


async def observe(duration, cached_services=False, all_services=False, automatic_address=False, device_name=None):
    deadline = time.monotonic() + 25
    matches = []
    while not matches and time.monotonic() < deadline:
        devices = await BleakScanner.discover(timeout=5, return_adv=True)
        matches = [d for d, a in devices.values() if
                   IDENTITY_SERVICE in [s.lower() for s in a.service_uuids] or
                   (device_name is not None and a.local_name == device_name and
                    SERVICE in [s.lower() for s in a.service_uuids])]
    if len(matches) != 1:
        raise RuntimeError(f'Expected exactly one PactoBridge identity advertiser; found {len(matches)}. No sensor selected.')
    advertised = [s.lower() for s in devices[matches[0].address][1].service_uuids]
    print(json.dumps({'stage': 'PactoBridge_identity_seen', 'advertised_services': advertised}), flush=True)
    options = {'use_cached_services': cached_services}
    raw = matches[0].details
    advertisement = getattr(raw, 'adv', None) or getattr(raw, 'scan', None)
    address_type = getattr(advertisement, 'bluetooth_address_type', None)
    if not automatic_address and address_type is not None and int(address_type) in (0, 1):
        options['address_type'] = 'random' if int(address_type) == 1 else 'public'
    print(json.dumps({'stage': 'opening_GATT', 'address': matches[0].address,
                      'cached_services': cached_services,
                      'address_type': options.get('address_type', 'auto')}), flush=True)
    frames = []
    stale = False
    disconnected = asyncio.Event()
    origin = time.monotonic()
    async with BleakClient(matches[0], services=None if all_services else [SERVICE, IDENTITY_SERVICE], winrt=options,
                           timeout=35, disconnected_callback=lambda c: disconnected.set()) as client:
        print(json.dumps({'stage': 'GATT_connected'}), flush=True)
        identity = bytes(await client.read_gatt_char(IDENTITY_VALUE))
        if identity != b'PB-PACTO-LIVE-1':
            raise RuntimeError('Remote endpoint is not the expected live PactoBridge')
        features = bytes(await client.read_gatt_char(FEATURE))
        if features != b'\x00\x00':
            raise RuntimeError('RSC feature set differs from expected PactoBridge output')

        def receive(characteristic, data):
            packet = bytes(data)
            if len(packet) != 4 or packet[0] != 0:
                raise ValueError('Unexpected RSC packet shape')
            _, units, cadence = struct.unpack('<BHB', packet)
            row = {'elapsed_s': time.monotonic()-origin, 'hex': packet.hex(' '),
                   'kmh': units/256*3.6, 'cadence': cadence}
            frames.append(row)
            if len(frames) == 1 or frames[-2]['hex'] != row['hex']:
                print(json.dumps({'kind': 'live_rsc', **row}), flush=True)

        await client.start_notify(MEASUREMENT, receive)
        print(json.dumps({'stage': 'RSC_subscribed', 'feature_hex': features.hex()}), flush=True)
        end = time.monotonic()+duration
        while time.monotonic() < end and not disconnected.is_set():
            try:
                await asyncio.wait_for(disconnected.wait(), timeout=min(1, end-time.monotonic()))
            except TimeoutError:
                if frames and time.monotonic()-origin-frames[-1]['elapsed_s'] > 4:
                    stale = True
                    break
        if client.is_connected:
            try:
                await client.stop_notify(MEASUREMENT)
            except (OSError, BleakError):
                # Windows can retain is_connected after the phone closes GATT.
                pass
    if not frames:
        raise RuntimeError('No live RSC measurements received')
    return {'source': 'actual PactoBridge BLE RSC notifications', 'device_name': matches[0].name,
            'identity_verified': True,
            'frames': frames, 'received': len(frames), 'disconnected': disconnected.is_set(),
            'ended_on_stale_stream': stale}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=float, default=45)
    parser.add_argument('--cached-services', action='store_true',
                        help='Diagnostic: reuse Windows service cache, still verify remote marker/features')
    parser.add_argument('--all-services', action='store_true', help='Diagnostic: unfiltered service discovery')
    parser.add_argument('--automatic-address', action='store_true', help='Diagnostic: let WinRT select address type')
    parser.add_argument('--device-name', help='Exact phone name fallback when scan responses are unavailable; remote identity is still required')
    args = parser.parse_args()
    if not 1 <= args.duration <= 600:
        parser.error('duration must be 1..600 seconds')
    result = asyncio.run(observe(args.duration, args.cached_services, args.all_services, args.automatic_address, args.device_name))
    directory = Path('captures/android')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f's22plus-live-rsc-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({'capture': str(path), 'received': result['received']}))


if __name__ == '__main__':
    main()
