def uuid16(value: int) -> str:
    return f"0000{value:04x}-0000-1000-8000-00805f9b34fb"


VENDOR_SERVICE = uuid16(0xFFF0)
FFF1 = uuid16(0xFFF1)
FFF2 = uuid16(0xFFF2)
VENDOR_CHANNELS = frozenset((FFF1, FFF2))
RSC_SERVICE = uuid16(0x1814)
RSC_MEASUREMENT = uuid16(0x2A53)
RSC_FEATURE = uuid16(0x2A54)
