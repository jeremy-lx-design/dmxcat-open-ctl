"""CLI: print the DMX universe the DMXcat currently holds.

When the device is receiving external DMX this is the received universe.
Uses the reference client in ../dmxcat.py.

Usage: dmx_read.py [address] [collect_seconds]
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dmxcat import DMXcat  # noqa: E402


async def main():
    collect = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
    dev = DMXcat(sys.argv[1]) if len(sys.argv) > 1 else await DMXcat.discover()
    async with dev:
        uni = await dev.read_received_universe(collect=collect)
    print(f"address: {dev.address}")
    print(f"start code: 0x{uni.start_code:02x}")
    nz = uni.channels()
    if nz:
        print("channels:")
        for ch, v in nz.items():
            print(f"  ch{ch} = {v}")
    else:
        print("(no channels pushed - is the device receiving DMX / blinking per packet?)")


if __name__ == "__main__":
    asyncio.run(main())
