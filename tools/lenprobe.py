"""Clean-room characteristic length prober.

For each target characteristic, writes all-zero payloads of increasing length
and records which lengths the device accepts vs. rejects with
"Invalid Attribute Value Length". This maps each register's expected size(s)
without assuming anything about payload meaning.
"""
import asyncio
import sys

from bleak import BleakClient

BASE = "-8000-0010-8000-00805f9bc171"
ADDR = "DC:68:DA:B2:EE:05"


def expand(short):
    return f"c171{short}{BASE}" if len(short) == 4 else short


async def main(chars, maxlen):
    async with BleakClient(ADDR, timeout=30.0) as client:
        print(f"connected={client.is_connected}\n")
        for short in chars:
            uuid = expand(short)
            accepted = []
            for n in range(0, maxlen + 1):
                payload = bytes(n)
                try:
                    await client.write_gatt_char(uuid, payload, response=True)
                    accepted.append(n)
                except Exception as e:  # noqa: BLE001
                    msg = str(e)
                    if "Invalid Attribute Value Length" in msg:
                        pass  # wrong length, keep probing
                    else:
                        print(f"  {short} len={n}: OTHER ERROR: {msg}")
                        if not client.is_connected:
                            print(f"  {short}: DISCONNECTED at len={n}")
                            return
                await asyncio.sleep(0.03)
            print(f"{short}: accepted lengths = {accepted}")


if __name__ == "__main__":
    maxlen = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    chars = sys.argv[2:] if len(sys.argv) > 2 else [
        "c101", "c103", "c104", "c105", "c106", "c107", "c109",
    ]
    asyncio.run(main(chars, maxlen))
