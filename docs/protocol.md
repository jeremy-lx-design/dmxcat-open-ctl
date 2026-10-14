# DMXcat BLE Protocol — Clean-Room Specification

> **Clean-room provenance.** Everything in this document was derived **solely by
> observing the device's own BLE behaviour** — its advertisements, its GATT
> table, and its responses to reads/writes — plus a known DMX signal injected on
> the wire for verification. No proprietary firmware, no official-app code, and
> no third-party reverse-engineering notes were consulted. Where a fact is
> directly observed it is marked **Verified**; where it is a reasoned
> interpretation it is marked **Inferred**.

Device under test: `DMXcat_600022729`, model `6000` (the smallest-memory SKU,
an ATmega-class controller). Firmware `1.4.1.9.0.168`, software `1.5.0.9.0.14`.

---

## 1. Transport & discovery

| Property | Value |
|----------|-------|
| Radio | Bluetooth Low Energy (GATT) |
| ATT MTU | 23 bytes (18 usable payload bytes per notification) |
| Advertised name | `DMXcat_<serial>` (e.g. `DMXcat_600022729`) |
| Adv. manufacturer data | company ID `0x4354` = ASCII **"CT"** (City Theatrical); payload e.g. `c99ec323` |
| Connection | single central at a time |

**Verified.** The vendor uses an unregistered company ID whose bytes spell
"CT". The device advertises with a slow blink; once a central connects it
switches to activity indication (e.g. one blink per received DMX packet).

---

## 2. GATT table

### 2.1 Standard services
- `0x1800` Generic Access — Device Name (`0x2A00`, read/write).
- `0x1801` Generic Attribute — Service Changed (indicate).
- `0x180A` Device Information:
  | Char | Field | Value on DUT |
  |------|-------|--------------|
  | `0x2A29` | Manufacturer | `City Theatrical, Inc.` |
  | `0x2A24` | Model Number | `6000` |
  | `0x2A25` | Serial Number | `600022729` |
  | `0x2A26` | Firmware Rev | `1.4.1.9.0.168` |
  | `0x2A28` | Software Rev | `1.5.0.9.0.14` |
- `0x180F` Battery Service — Battery Level (`0x2A19`, read/notify, %).
- `0x1802` Immediate Alert — Alert Level (`0x2A06`, write-no-response). The
  device has an audible buzzer; some command paths make it beep.

### 2.2 Vendor services (128-bit base `........-8000-0010-8000-00805f9bc171`)

The 128-bit base ends in `c171` ("C1 71"). Two vendor services exist.

#### Service `c171b007…` — command/control transport
| Char | Properties | Role |
|------|-----------|------|
| `c171b017` | write / indicate | control channel, response prefix `0x20` — **destructive** (see §6) |
| `c171b107` | write / notify | **command channel**, response prefix `0x60` (see §4) |
| `c171b207` | write-no-response | bulk-data channel (purpose unconfirmed) |

#### Service `c171c100…` — DMX/data + diagnostics
| Char | Properties | Max write | Readable | Role |
|------|-----------|-----------|----------|------|
| `c171c101` | read/write/write-nr/notify | 5 | yes (`00 00 00 00 00`) | config register |
| `c171c102` | read/write-nr/notify | 20 | yes (`01`) | **DMX universe buffer** (see §3) |
| `c171c103` | write/write-nr | 20 | no | data channel (unconfirmed) |
| `c171c104` | write/write-nr | 2 | no | 2-byte register |
| `c171c105` | write/indicate | 1 | no | **diagnostics command register** (see §5) |
| `c171c106` | write/notify/indicate | 2 | no | status register (`0000`/`0200`) |
| `c171c107` | write/notify | 20 | no | telemetry/response channel (see §5) |
| `c171c108` | notify | — | no | async event channel |
| `c171c109` | write/indicate | 20 | no | data/response channel |
| `c171c10a` | write/indicate | ? | no | **destructive** – powers down (see §6) |
| `c171c10b` | write | ? | no | command (unmapped) |
| `c171c10e` | write | ? | no | command (unmapped) |

**Verified** accepted write lengths (all-zero payloads; a wrong length is
rejected with GATT *Invalid Attribute Value Length*):
```
c101: 0..5   c103: 0..20   c104: 0..2   c105: 0..1
c106: 0..2   c107: 0..20   c109: 0..20
```
(20 is the ATT-MTU cap, not necessarily a protocol limit.)

---

## 3. The DMX universe buffer — characteristic `c102`  **(Verified)**

`c102` carries a DMX frame buffer, chunked across notifications:

```
notification = [ offset : uint16 little-endian ][ up to 18 data bytes ]
slot 0      = DMX start code (0x00 for a standard null-start-code frame)
slot N (1..512) = DMX channel N
```
Chunks step by 18: offsets `0, 18, 36, … 504`.

Two ways the device emits the buffer:

- **Enable notifications (write CCCD = 0x0001) → the device pushes the buffer.**
  Only populated blocks are sent. To re-read, toggle notifications off then on.
- **Read the characteristic →** returns the 1-byte value `0x01` and triggers a
  full dump of all 512 slots.

### 3.1 Reading received DMX  **(Verified, incl. live tracking)**

When an external DMX source drives the device's port, the buffer **is the
received universe**. Procedure:

1. Connect.
2. Enable notifications on `c102`.
3. Reassemble chunks into a 513-byte array (`slot 0` = start code).
4. `channel[N] = array[N]` for N in 1..512.

Verification: feeding a stable frame of
`ch1=224, ch2=128, ch10=96, ch11=240, ch12=240, ch14=96, ch15=64, ch16=96`
produced exactly:
```
slot 0  = 0x00   (start code)
slot 1  = 224    slot 2  = 128
slot 10 = 96     slot 11 = 240   slot 12 = 240
slot 14 = 96     slot 15 = 64    slot 16 = 96
all others = 0
```
Changing channel 11 from 240→224 on the source was reflected on the next read —
confirming **live** reception. See `tools/dmx_read.py` for a reference reader.

**State note.** The device only emits these pushes while it is actively in its
receive state — indicated by a per-packet LED blink. The push is produced when
notifications are (re-)enabled on `c102`, so a robust reader toggles notify and
retries. Heavy BLE command activity (e.g. sweeping `c105`) can knock the device
out of this state until it is power-cycled.

### 3.2 DMX output (controller)  **(Partially mapped)**

The same `c102` buffer mirrors the **output** universe when the device is in
controller mode. Reading `c102` while idle dumps all-zero slots. The command
that enters controller mode and the channel-set write path were **not** safely
isolated: the likely controller/function-select commands live on the
destructive `c171b017` channel (§6), which drops the link when probed, so this
path was left unconfirmed to avoid repeatedly downing the device.

---

## 4. Command channel `c171b107`  **(Verified framing)**

Write an opcode (optionally followed by arguments); the device replies with a
notification on `c171b107`:
```
response = 0x60  <opcode-echo>  <status/payload …>
status 0x03  = unknown / unsupported opcode
status 0x01  = OK, followed by payload bytes
```
Recognised no-argument opcodes on this SKU:

| Opcode | Response | Notes |
|--------|----------|-------|
| `0x03` | `60 03 01` + 8 bytes (all `00`) | getter; value independent of DMX in/out |
| `0x04` | `60 04 05` | getter returning constant `0x05` |
| `0x0a` | `60 0a 01 80 16 12 03 00 00 00 00 00 40 00 00` | 12-byte config/capability struct |
| all others `0x00..0xff` | `60 <op> 03` | unknown opcode |

The sibling channel `c171b017` uses the same shape with response prefix `0x20`
but is destructive (§6).

---

## 5. Diagnostics register `c171c105`  **(Partially decoded)**

Writing a 1-byte opcode to `c105` drives a measurement/diagnostic subsystem and
produces responses on `c106`, `c107`, `c108`. Opcode structure: the **low 3
bits select an action**, the upper bits select a target/index.

| `op & 0x07` | Reaction |
|-------------|----------|
| 0 | `c106` → `0200` (busy/active) **and** `c107` 16-byte telemetry |
| 1 | `c107` 16-byte telemetry |
| 3 | `c108` → `03` |
| 6 | `c106` → `0000` (idle) |

`c107` telemetry frame (16 bytes), constant header then a value that **tracks
the DMX line state** (changes when a signal is present):
```
5b 00 08 00 2f 00 0b 00 | <b8..b9> | <byte10> | <uint32 measurement>
```
This is consistent with a DMX/cable line-measurement tool. Exact units were not
determined (needs controlled electrical stimulus). **Caution:** some `c105`
opcodes trigger the buzzer and switch the device out of DMX-receive mode until
it is power-cycled/reconnected, so sweep this register sparingly.

---

## 6. Destructive / power commands  **(Verified — avoid)**

| Command | Effect |
|---------|--------|
| Write to `c171c10a` (e.g. 3-byte payload) | immediate disconnect; device stops advertising / powers down |
| Write to `c171b017` (e.g. opcode `0x02`, also `0x01`) | drops the BLE link |

After these, the device **re-advertises on its own after ~1–2 minutes** (no
physical button press needed), or can be power-cycled.

---

## 7. Practical recipes

**Read the received DMX universe**
1. Connect to `DMXcat_<serial>`.
2. `start_notify(c171c102…)` and collect chunks for ~1.5 s.
3. Parse `[offset:LE16][data]`; `channel[N]=buf[N]`, `buf[0]`=start code.
4. Re-poll by toggling notify off/on.

**Query device config**
- Write `0x0a` to `c171b107`; read the 12-byte struct from the `60 0a 01 …`
  response. Write `0x03`/`0x04` for the other getters.

**Things to avoid** — writing to `c171c10a` or `c171b017` (drops the link), and
blind sweeping of `c171c105` (buzzer + leaves DMX-receive mode).

---

## 8. Status summary

| Area | State |
|------|-------|
| Advertising / identity / GATT map | ✅ Verified |
| Characteristic write-length profiles | ✅ Verified |
| `c102` DMX buffer framing | ✅ Verified |
| **DMX reception (read received universe, live)** | ✅ Verified end-to-end |
| `b107` command framing + getters | ✅ Verified |
| `c105` diagnostics structure | 🟡 Partially decoded |
| DMX output / controller set-path | 🟡 Mechanism located (`c102` mirror), enable command unconfirmed |
| `c107` telemetry units | 🟡 Open |
| `b017` / `c10a` semantics | ✅ Identified as destructive |
