"""Read-only WFTNP discovery/actual-RSC receiver. Never connects to or controls Pacto."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import time
from uuid import UUID

SERVICE_TYPE = '_wahoo-fitness-tnp._tcp.local.'
RSC = UUID('00001814-0000-1000-8000-00805f9b34fb').bytes
FEATURE = UUID('00002a54-0000-1000-8000-00805f9b34fb').bytes
MEASUREMENT = UUID('00002a53-0000-1000-8000-00805f9b34fb').bytes
SERIAL = UUID('00002a25-0000-1000-8000-00805f9b34fb').bytes


async def discover(interface):
    from zeroconf import IPVersion, ServiceBrowser, Zeroconf
    names = set()

    class Listener:
        def add_service(self, zc, service_type, name):
            if name.startswith('PactoBridge WiFi '):
                names.add(name)
        update_service = add_service
        def remove_service(self, zc, service_type, name):
            names.discard(name)

    zc = Zeroconf(interfaces=[interface], ip_version=IPVersion.V4Only)
    browser = ServiceBrowser(zc, SERVICE_TYPE, Listener())
    try:
        end = time.monotonic()+20
        while not names and time.monotonic() < end:
            await asyncio.sleep(.2)
        if len(names) != 1:
            raise RuntimeError(f'Expected one PactoBridge WiFi service; found {len(names)}')
        info = await asyncio.to_thread(zc.get_service_info, SERVICE_TYPE, next(iter(names)), 4000)
        if info is None or not info.parsed_addresses(IPVersion.V4Only):
            raise RuntimeError('Service address could not be resolved')
        return {'name': info.name, 'host': info.parsed_addresses(IPVersion.V4Only)[0],
                'port': info.port, 'attributes': {k.decode(): v.decode() for k, v in info.properties.items()}}
    finally:
        browser.cancel()
        await asyncio.to_thread(zc.close)


async def receive(reader):
    version, kind, seq, status, size = struct.unpack('!BBBBH', await reader.readexactly(6))
    if version != 1 or size > 4096:
        raise RuntimeError('Invalid WFTNP framing')
    return kind, seq, status, await reader.readexactly(size)


async def probe(args):
    endpoint = {'host': args.host, 'port': args.port} if args.host else await discover(args.interface)
    print(json.dumps({'stage': 'wifi_endpoint', **endpoint}), flush=True)
    reader, writer = await asyncio.wait_for(asyncio.open_connection(endpoint['host'], endpoint['port']), 5)
    sequence = 0

    async def request(kind, body=b''):
        nonlocal sequence
        sequence = (sequence+1) % 256
        writer.write(struct.pack('!BBBBH', 1, kind, sequence, 0, len(body))+body)
        await writer.drain()
        msg = await asyncio.wait_for(receive(reader), 5)
        if msg[:3] != (kind, sequence, 0):
            raise RuntimeError(f'Unexpected WFTNP reply {msg[:3]}')
        return msg[3]

    frames = []
    try:
        services = await request(1)
        if RSC not in [services[i:i+16] for i in range(0, len(services), 16)]:
            raise RuntimeError('No RSC service')
        features = await request(3, FEATURE)
        serial = await request(3, SERIAL)
        if features != FEATURE+b'\0\0' or not serial.startswith(SERIAL+b'PB22-'):
            raise RuntimeError('Not the expected PactoBridge read-only RSC endpoint')
        print(json.dumps({'stage': 'wifi_profile_verified', 'serial': serial[16:].decode()}), flush=True)
        if args.subscribe:
            await request(5, MEASUREMENT+b'\1')
            print(json.dumps({'stage': 'wifi_RSC_subscribed'}), flush=True)
            origin = time.monotonic()
            end = origin+args.duration
            while time.monotonic() < end:
                try:
                    kind, _, status, body = await asyncio.wait_for(receive(reader), min(2, end-time.monotonic()))
                except TimeoutError:
                    if frames and time.monotonic()-origin-frames[-1]['elapsed_s'] > 4:
                        break
                    continue
                except asyncio.IncompleteReadError:
                    break
                if kind != 6 or status != 0 or len(body) != 20 or body[:16] != MEASUREMENT or body[16] != 0:
                    raise RuntimeError('Unexpected actual RSC notification')
                _, units, cadence = struct.unpack('<BHB', body[16:])
                row = {'elapsed_s': time.monotonic()-origin, 'hex': body[16:].hex(' '),
                       'kmh': units/256*3.6, 'cadence': cadence}
                frames.append(row)
                if len(frames) == 1 or frames[-2]['hex'] != row['hex']:
                    print(json.dumps({'kind': 'live_wifi_rsc', **row}), flush=True)
        return {'source': 'actual Android WFTNP responses/RSC notifications', 'endpoint': endpoint,
                'profile_verified': True, 'subscribed': args.subscribe, 'frames': frames, 'received': len(frames)}
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interface', help='LAN IPv4 interface for mDNS, not VPN')
    parser.add_argument('--host', help='Diagnostic direct phone IP; requires --port')
    parser.add_argument('--port', type=int)
    parser.add_argument('--subscribe', action='store_true')
    parser.add_argument('--duration', type=float, default=90)
    args = parser.parse_args()
    if not args.interface and not (args.host and args.port):
        parser.error('Supply LAN --interface or both --host and --port')
    if not 1 <= args.duration <= 600:
        parser.error('duration must be 1..600 seconds')
    result = asyncio.run(probe(args))
    path = Path('captures/android') / f's22plus-wifi-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'capture': str(path), 'received': result['received']}))
    if args.subscribe and not result['frames']:
        raise SystemExit('No live source measurements received; no speed was generated')


if __name__ == '__main__':
    main()
