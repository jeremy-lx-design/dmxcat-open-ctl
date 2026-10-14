"""Clean-room opcode sweeper.

Writes single-byte (or prefixed) opcodes across a range to a target
characteristic. After each write it reads back the readable status registers
and reports any CHANGE from baseline, and logs any notification/indication
received. This surfaces which opcodes cause an observable device reaction.
"""
import asyncio
import sys
import time

from bleak import BleakClient

BASE = "-8000-0010-8000-00805f9bc171"
ADDR = "DC:68:DA:B2:EE:05"
START = time.monotonic()

READBACKS = ["c101"]  # only c101 is a readable status register (besides c102 dump)


def expand(short):
    return f"c171{short}{BASE}" if len(short) == 4 else short


def ts():
    return f"{time.monotonic()-START:7.3f}s"


async def readback(client):
    out = {}
    for short in READBACKS:
        try:
            v = await client.read_gatt_char(expand(short))
            out[short] = bytes(v).hex()
        except Exception:  # noqa: BLE001
            out[short] = "?"
    return out


async def main(target, lo, hi, prefix, settle=0.15, preamble=None):
    events = []

    def cb(char, data):
        u = char.uuid
        sh = u[4:8] if u.startswith("c171") else u[:8]
        events.append((sh, bytes(data).hex()))

    async with BleakClient(ADDR, timeout=30.0) as client:
        print(f"connected={client.is_connected} target={target} prefix={prefix!r}")
        for service in client.services:
            for ch in service.characteristics:
                if ("notify" in ch.properties or "indicate" in ch.properties):
                    try:
                        await client.start_notify(ch, cb)
                    except Exception:  # noqa: BLE001
                        pass
        if preamble:
            pch, phex = preamble.split("=")
            events.clear()
            await client.write_gatt_char(expand(pch), bytes.fromhex(phex), response=True)
            await asyncio.sleep(0.5)
            print(f"preamble {pch}={phex} -> NOTIFY {events}")
        base = await readback(client)
        print(f"baseline: {base}")
        for op in range(lo, hi + 1):
            events.clear()
            payload = bytes.fromhex(prefix) + bytes([op])
            try:
                await client.write_gatt_char(expand(target), payload, response=True)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                short = "LENERR" if "Value Length" in msg else msg[:40]
                print(f"op={op:#04x} write-err: {short}")
                if not client.is_connected:
                    print("DISCONNECTED"); return
                continue
            await asyncio.sleep(settle)
            now = await readback(client)
            changes = {k: (base[k], now[k]) for k in now if now[k] != base[k]}
            note = ""
            if changes:
                note = "  CHANGED " + " ".join(f"{k}:{a}->{b}" for k, (a, b) in changes.items())
            if events:
                note += "  NOTIFY[" + " ".join(f"{s}={d}" for s, d in events) + "]"
            if note:
                print(f"op={op:#04x} payload={payload.hex()}{note}")
            base = now
    print("done")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "c101"
    lo = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    hi = int(sys.argv[3]) if len(sys.argv) > 3 else 32
    prefix = sys.argv[4] if len(sys.argv) > 4 else ""
    if prefix in ("-", "none"):
        prefix = ""
    settle = float(sys.argv[5]) if len(sys.argv) > 5 else 0.15
    preamble = sys.argv[6] if len(sys.argv) > 6 else None
    asyncio.run(main(target, lo, hi, prefix, settle, preamble))
