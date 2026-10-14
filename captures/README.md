# Capture evidence

Raw observation logs that back the specification in `../docs/protocol.md`.
All were produced by the tools in `../tools/` talking to the device as a
generic BLE central (plus a known DMX source for the reception captures).

| File | What it shows |
|------|---------------|
| `gatt_enum_initial.txt` | Full GATT dump: services, characteristics, properties, initial values (device identity). |
| `sweep_b107_0_63.txt` | `b107` command-channel opcode map — `60 <op> <status>` framing; getters `0x03`, `0x04`, `0x0a`. |
| `sweep_c105_full.txt` | `c105` diagnostics register — low-3-bits action structure and `c106`/`c107`/`c108` responses. |
| `rx_fresh.txt` | First capture of the **received** DMX universe on `c102` matching a known injected frame. |
| `rx_frame.txt` | Clean single received dump — proves `offset 0 = start code`, `offset N = channel N`. |
| `rx_resub.txt` | Re-subscribing to `c102` re-pushes the received universe (the poll mechanism). |
