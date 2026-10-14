"""dmxcat — clean-room reference client for the City Theatrical DMXcat BLE API.

Implements only the behaviours that were verified by observation (see
docs/protocol.md). Requires `bleak`.

Example
-------
    import asyncio
    from dmxcat import DMXcat

    async def main():
        dev = await DMXcat.discover()          # find first DMXcat advertising
        async with dev:
            uni = await dev.read_received_universe()
            print("start code:", uni.start_code)
            print("channels:", uni.channels())   # {ch: value} for nonzero
            print("config:", (await dev.get_config()).hex())

    asyncio.run(main())
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner

_BASE = "-8000-0010-8000-00805f9bc171"
C102 = f"c171c102{_BASE}"          # DMX universe buffer
B107 = f"c171b107{_BASE}"          # command channel
NAME_PREFIX = "DMXcat"
VENDOR_COMPANY_ID = 0x4354         # "CT"


@dataclass
class Universe:
    """A DMX frame: start code + 512 channel slots (1-indexed)."""
    data: bytearray   # length 513; index 0 = start code, 1..512 = channels

    @property
    def start_code(self) -> int:
        return self.data[0]

    def channel(self, n: int) -> int:
        if not 1 <= n <= 512:
            raise ValueError("channel out of range 1..512")
        return self.data[n]

    def channels(self) -> dict[int, int]:
        """Nonzero channels as {channel: value}."""
        return {n: self.data[n] for n in range(1, 513) if self.data[n]}


class DMXcat:
    def __init__(self, address: str):
        self.address = address
        self._client = BleakClient(address, timeout=30.0)

    # ---- discovery ----
    @staticmethod
    async def discover(timeout: float = 10.0) -> "DMXcat":
        """Return the first advertising DMXcat (by name prefix / company id)."""
        found: dict[str, str] = {}

        def cb(device, adv):
            name = adv.local_name or device.name or ""
            if name.startswith(NAME_PREFIX) or VENDOR_COMPANY_ID in adv.manufacturer_data:
                found.setdefault(device.address, name)

        scanner = BleakScanner(detection_callback=cb)
        await scanner.start()
        for _ in range(int(timeout * 10)):
            if found:
                break
            await asyncio.sleep(0.1)
        await scanner.stop()
        if not found:
            raise RuntimeError("no DMXcat found")
        return DMXcat(next(iter(found)))

    # ---- connection ----
    async def __aenter__(self):
        await self._client.connect()
        return self

    async def __aexit__(self, *exc):
        await self._client.disconnect()

    # ---- DMX reception ----
    async def read_received_universe(self, collect: float = 1.5,
                                     attempts: int = 4) -> Universe:
        """Read the DMX universe currently in the device buffer.

        Enabling notifications on c102 makes the device push the buffer as
        [offset:uint16 LE][data] chunks. When the device is receiving external
        DMX this is the received universe. The push is emitted when
        notifications are (re-)enabled, so we toggle/retry to force it.

        Note: the device only pushes while it is actively in its receive state
        (it indicates this with a per-packet LED blink). That state can be lost
        after heavy BLE command activity and is restored by power-cycling.
        """
        buf = bytearray(513)
        got = {"any": False}

        def cb(_c, data: bytearray):
            raw = bytes(data)
            if len(raw) < 2:
                return
            off = raw[0] | (raw[1] << 8)
            for i, b in enumerate(raw[2:]):
                if off + i < len(buf):
                    buf[off + i] = b
            got["any"] = True

        for _ in range(attempts):
            await self._client.start_notify(C102, cb)  # (re-)enable triggers push
            waited = 0.0
            while waited < collect and not got["any"]:
                await asyncio.sleep(0.1)
                waited += 0.1
            await self._client.stop_notify(C102)
            if got["any"]:
                break
            await asyncio.sleep(0.2)
        return Universe(buf)

    # ---- command channel ----
    async def command(self, opcode: int, *args: int, collect: float = 0.4) -> bytes:
        """Send a b107 opcode and return the response payload (after `60 <op>`).

        Raises if the device reports status 0x03 (unknown opcode).
        """
        resp: list[bytes] = []
        ev = asyncio.Event()

        def cb(_c, data: bytearray):
            raw = bytes(data)
            if len(raw) >= 2 and raw[0] == 0x60 and raw[1] == opcode:
                resp.append(raw)
                ev.set()

        await self._client.start_notify(B107, cb)
        await self._client.write_gatt_char(B107, bytes([opcode, *args]), response=True)
        try:
            await asyncio.wait_for(ev.wait(), timeout=collect)
        except asyncio.TimeoutError:
            pass
        await self._client.stop_notify(B107)
        if not resp:
            raise RuntimeError(f"no response to opcode {opcode:#04x}")
        payload = resp[0][2:]
        if payload[:1] == b"\x03":
            raise RuntimeError(f"opcode {opcode:#04x} not supported (status 0x03)")
        return payload

    async def get_config(self) -> bytes:
        """b107 opcode 0x0a: 12-byte config/capability struct (after status byte)."""
        return (await self.command(0x0A))[1:]
