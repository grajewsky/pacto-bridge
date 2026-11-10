"""Connect only to PactoBridge's custom radio test, never the treadmill/RSC."""
import asyncio
import json
from bleak import BleakScanner, BleakClient

SERVICE = '9260b100-2460-4ce3-956a-f1a3d6e086f1'
VALUE = '9260b101-2460-4ce3-956a-f1a3d6e086f1'
EXPECTED = b'PB-RADIO-1'


async def main():
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: SERVICE in [s.lower() for s in adv.service_uuids], timeout=20)
    if device is None:
        raise RuntimeError('Custom Android radio diagnostic advertisement not found')
    print(json.dumps({'stage': 'advertisement_seen'}), flush=True)
    async with BleakClient(device, timeout=35, services=[SERVICE],
                           winrt={'use_cached_services': False}) as client:
        print(json.dumps({'stage': 'gatt_connected'}), flush=True)
        service = client.services.get_service(SERVICE)
        if service is None or service.get_characteristic(VALUE) is None:
            raise RuntimeError('Expected diagnostic GATT layout missing')
        value = bytes(await client.read_gatt_char(VALUE))
        if value != EXPECTED:
            raise RuntimeError('Unexpected diagnostic read value')
        received = asyncio.get_running_loop().create_future()
        def notification(characteristic, data):
            if not received.done():
                received.set_result(bytes(data))
        await client.start_notify(VALUE, notification)
        try:
            packet = await asyncio.wait_for(received, timeout=10)
            if packet != EXPECTED:
                raise RuntimeError('Unexpected diagnostic notification')
        finally:
            await client.stop_notify(VALUE)
        print(json.dumps({'advertisement_seen': True, 'connection': True,
            'service_discovery': True, 'read_value': value.decode(),
            'cccd_subscription': True, 'notification_value': packet.decode(),
            'treadmill_connected': False, 'rsc_speed_transmitted': False}))


if __name__ == '__main__':
    asyncio.run(main())
