"""Clean-room BLE discovery scanner.

Observes nearby BLE advertisements only. No proprietary code is used.
Prints each device's address, name, RSSI, advertised service UUIDs,
service data, and manufacturer data so we can identify the DMXcat.
"""
import asyncio
import sys

from bleak import BleakScanner


async def main(duration: float) -> None:
    seen = {}

    def on_detect(device, adv):
        seen[device.address] = (device, adv)

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    await asyncio.sleep(duration)
    await scanner.stop()

    print(f"\n=== Discovered {len(seen)} device(s) in {duration:.0f}s ===\n")
    for addr, (device, adv) in sorted(
        seen.items(), key=lambda kv: (kv[1][1].rssi or -999), reverse=True
    ):
        name = adv.local_name or device.name or "(no name)"
        print(f"{addr}  RSSI={adv.rssi}  name={name!r}")
        if adv.service_uuids:
            for u in adv.service_uuids:
                print(f"    service-uuid: {u}")
        if adv.service_data:
            for u, d in adv.service_data.items():
                print(f"    service-data[{u}]: {d.hex()}")
        if adv.manufacturer_data:
            for cid, d in adv.manufacturer_data.items():
                print(f"    mfr-data[0x{cid:04x}]: {d.hex()}")
        if adv.tx_power is not None:
            print(f"    tx_power: {adv.tx_power}")
        print()


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    asyncio.run(main(dur))
