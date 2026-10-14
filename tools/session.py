"""Clean-room interactive probe harness for the DMXcat.

Connects to the device, subscribes to every notify/indicate characteristic,
then executes a small reproducible script. All inbound notifications are
timestamped and logged. This is pure black-box observation of the device.

Script commands (one per line, read from a file or stdin via --cmd):
    # comment
    w   <char> <hex>     write WITH response
    wn  <char> <hex>     write WITHOUT response
    r   <char>           read characteristic
    sleep <seconds>
    rescan               re-read every readable characteristic

<char> may be a 4-hex-digit short form for a custom characteristic, e.g.
"c101" -> c171c101-8000-0010-8000-00805f9bc171, or a full UUID.
"""
import asyncio
import sys
import time

from bleak import BleakClient

BASE = "-8000-0010-8000-00805f9bc171"
START = time.monotonic()


def expand(short: str) -> str:
    s = short.lower()
    if len(s) == 4:
        return f"c171{s}{BASE}"
    return s


def ts() -> str:
    return f"{time.monotonic() - START:7.3f}s"


def ascii_preview(b: bytes) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)


def log_notify(char, data: bytearray):
    uuid = char.uuid
    short = uuid[4:8] if uuid.startswith("c171") else uuid[:8]
    print(f"[{ts()}] NOTIFY {short}  {bytes(data).hex():<40} |{ascii_preview(bytes(data))}|", flush=True)


async def run(address: str, lines):
    async with BleakClient(address, timeout=30.0) as client:
        print(f"[{ts()}] connected={client.is_connected}", flush=True)
        subscribed = []
        for service in client.services:
            for ch in service.characteristics:
                if "notify" in ch.properties or "indicate" in ch.properties:
                    try:
                        await client.start_notify(ch, log_notify)
                        subscribed.append(ch.uuid)
                    except Exception as e:  # noqa: BLE001
                        print(f"[{ts()}] subscribe-fail {ch.uuid}: {e}", flush=True)
        print(f"[{ts()}] subscribed to {len(subscribed)} characteristics", flush=True)

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            op = parts[0].lower()
            try:
                if op == "sleep":
                    await asyncio.sleep(float(parts[1]))
                elif op == "r":
                    uuid = expand(parts[1])
                    val = await client.read_gatt_char(uuid)
                    print(f"[{ts()}] READ   {parts[1]}  {bytes(val).hex()} |{ascii_preview(bytes(val))}|", flush=True)
                elif op in ("w", "wn"):
                    uuid = expand(parts[1])
                    payload = bytes.fromhex(parts[2]) if len(parts) > 2 else b""
                    await client.write_gatt_char(uuid, payload, response=(op == "w"))
                    print(f"[{ts()}] WROTE  {parts[1]} ({'resp' if op=='w' else 'no-resp'})  {payload.hex()}", flush=True)
                elif op == "sub":
                    await client.start_notify(expand(parts[1]), log_notify)
                    print(f"[{ts()}] SUB    {parts[1]}", flush=True)
                elif op == "unsub":
                    await client.stop_notify(expand(parts[1]))
                    print(f"[{ts()}] UNSUB  {parts[1]}", flush=True)
                elif op == "rescan":
                    for service in client.services:
                        for ch in service.characteristics:
                            if "read" in ch.properties:
                                try:
                                    v = await client.read_gatt_char(ch)
                                    sh = ch.uuid[4:8] if ch.uuid.startswith("c171") else ch.uuid[:8]
                                    print(f"[{ts()}] STATE  {sh}  {bytes(v).hex()} |{ascii_preview(bytes(v))}|", flush=True)
                                except Exception:  # noqa: BLE001
                                    pass
                else:
                    print(f"[{ts()}] ?? unknown op: {line}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[{ts()}] ERROR on '{line}': {e}", flush=True)
        await asyncio.sleep(0.5)
        print(f"[{ts()}] done", flush=True)


def main():
    address = "DC:68:DA:B2:EE:05"
    cmd = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--addr":
            address = args[i + 1]; i += 2
        elif args[i] == "--cmd":
            cmd = args[i + 1]; i += 2
        elif args[i] == "--file":
            with open(args[i + 1]) as f:
                cmd = f.read(); i += 2
        else:
            i += 1
    lines = cmd.split(";") if cmd else sys.stdin.read().splitlines()
    asyncio.run(run(address, lines))


if __name__ == "__main__":
    main()
