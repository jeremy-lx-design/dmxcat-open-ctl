# dmxcat-proto

**A clean-room reverse-engineering of the City Theatrical DMXcat Bluetooth LE
protocol**, so anyone can integrate the device into their own apps.

The DMXcat is a BLE DMX-512 interface/tester that normally only talks to its
vendor mobile app. This project documents its wire protocol — purely by
observing the device's own behaviour — and ships a small reference client.

## Clean-room statement

Everything here was derived **only** from:
- the device's BLE advertisements and GATT table,
- its responses to reads/writes we sent as a generic BLE central, and
- a known DMX signal injected on the wire, used to verify decoding.

**No** official-app code, firmware images, or third-party reverse-engineering
were examined. See [`docs/protocol.md`](docs/protocol.md) for the specification,
with every claim marked *Verified* or *Inferred*.

## What works today

- ✅ **Read the received DMX universe** over BLE — verified channel-for-channel
  against a known source, including live updates.
- ✅ Full GATT map, device identity, and characteristic write-length profiles.
- ✅ `b107` command-channel framing (`60 <op> <status> [payload]`) + getters.
- ✅ Identified the destructive commands to avoid.
- 🟡 DMX **output**/controller path and `c105` line-telemetry units: partially
  mapped (see spec §3.2, §5).

## Quick start

```bash
python -m venv .venv
.venv/Scripts/python -m pip install bleak        # Windows
# source .venv/bin/activate && pip install bleak # Linux/macOS

# read whatever DMX the DMXcat is currently receiving:
python tools/dmx_read.py
```

Or use the library:

```python
import asyncio
from dmxcat import DMXcat

async def main():
    dev = await DMXcat.discover()
    async with dev:
        uni = await dev.read_received_universe()
        print("start code:", uni.start_code)
        print("channels:", uni.channels())   # {channel: value}

asyncio.run(main())
```

## Repository layout

```
dmxcat.py            Reference client library (verified protocol only)
docs/protocol.md     The clean-room protocol specification
tools/               Exploration/verification tools used to derive the spec:
  ble_scan.py          BLE advertisement scanner
  gatt_enum.py         Full GATT service/characteristic dump
  session.py           Scripted read/write/subscribe harness with logging
  decode.py            Reassembles c102 chunk dumps
  opsweep.py           Opcode sweeper for command registers
  lenprobe.py          Characteristic write-length prober
  dmx_read.py          CLI: print the received DMX universe
firmware/            Arduino DMX bridge used to inject/observe DMX on the wire
captures/            Raw observation logs (evidence trail)
```

## Hardware used to verify

A generic BLE adapter (as the central) plus — for feeding/observing real DMX — an
Arduino + auto-direction RS485 (MAX485/CD4069) module. The Arduino bridge
firmware is in `firmware/` and is optional; reception decoding only needs the
BLE adapter and any standard DMX source.

## Status & contributions

This is an interoperability effort; the protocol surface is incompletely mapped
(notably the controller/output set-path). Issues and PRs that extend the spec —
with observations, not vendor code — are welcome. No warranty; use at your own
risk (some commands can momentarily drop or power-cycle the device).
