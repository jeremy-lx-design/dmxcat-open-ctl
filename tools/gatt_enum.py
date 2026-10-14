"""Clean-room GATT enumerator.

Connects to a BLE device by address and dumps the full attribute table:
services, characteristics (with properties), descriptors, and the current
value of every readable characteristic. Pure black-box observation.
"""
import asyncio
import sys

from bleak import BleakClient


def safe_hex(b: bytes) -> str:
    return b.hex() if b is not None else ""


def ascii_preview(b: bytes) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)


async def main(address: str) -> None:
    print(f"Connecting to {address} ...")
    async with BleakClient(address, timeout=30.0) as client:
        print(f"Connected: {client.is_connected}\n")
        for service in client.services:
            print(f"[service] {service.uuid}  ({service.description})")
            for ch in service.characteristics:
                props = ",".join(ch.properties)
                print(f"  [char] {ch.uuid}  handle=0x{ch.handle:04x}  props=[{props}]  ({ch.description})")
                if "read" in ch.properties:
                    try:
                        val = await client.read_gatt_char(ch)
                        print(f"        value: {safe_hex(val)}  |{ascii_preview(val)}|")
                    except Exception as e:  # noqa: BLE001
                        print(f"        value: <read error: {e}>")
                for d in ch.descriptors:
                    try:
                        dval = await client.read_gatt_descriptor(d.handle)
                        print(f"      [desc] {d.uuid}  handle=0x{d.handle:04x}  value={safe_hex(dval)} |{ascii_preview(dval)}|")
                    except Exception as e:  # noqa: BLE001
                        print(f"      [desc] {d.uuid}  handle=0x{d.handle:04x}  <read error: {e}>")
            print()


if __name__ == "__main__":
    addr = sys.argv[1] if len(sys.argv) > 1 else "DC:68:DA:B2:EE:05"
    asyncio.run(main(addr))
