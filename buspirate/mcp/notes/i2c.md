# I2C: two wires, 7-bit addresses, pull-ups required

## Wiring

| Signal | v3/v4 (Seeed) | BP6 | Bit Pirate dock |
|---|---|---|---|
| SCL | CLK, purple | IO1, yellow | IO16, yellow |
| SDA | MOSI, grey | IO0, orange | IO15, orange |
| GND | brown | black | black |
| Pull-up rail | VPU, green | VOUT (red) | internal ~45 kΩ |

GND first. Power the target from the Bus Pirate only if nothing else powers
it (see the power note).

## Pull-ups: what usually goes wrong

I2C lines are open-drain; something must pull them up.

- If the module has its own pull-ups (most breakouts do), leave the Bus
  Pirate's **off**. Verified: an AHT20 + BMP280 module scanned cleanly with
  pull-ups off; with them on and VPU unconnected a v4 reported 18 phantom
  addresses.
- v3/v4: the pull-ups pull to VPU. Tie VPU to the bus's rail, or on a v4
  select the internal 3.3 V / 5 V rail in software (refused if a voltage is
  already on VPU). **VPU floating: every address seems to answer**, because
  SDA held low reads as an ACK.
- BP6: one switch turns on 10 kΩ pull-ups to VOUT; VOUT needs a voltage.
- Bit Pirate: `P` / `p` switch the ESP32's internal pull-ups.

## Addresses and speeds

- Use the **7-bit** address (`0x50`, not `0xA0`); the R/W bit is added for
  you. Scans normally cover 0x08–0x77.
- v3/v4 speeds: 5 kHz, 50 kHz, 100 kHz (the usual choice), 400 kHz.
  Firmware older than v4.2 has only 5 and 50 kHz.
- Long wires and weak pull-ups slow the edges: if 400 kHz is flaky, drop to
  100 kHz first.

## Reading registers

- `read_register()` writes the register number, does a repeated start, then
  reads. Correct on every firmware; use it by default.
- `write_then_read()` (v3/v4 firmware v5.1+) is faster for bulk reads but has
  **no repeated start**.
- Bit Pirate: `[0x68 0x00 r:8]` writes register 0x00 to address 0x68 and
  reads 8 bytes after a repeated start.

## When a scan finds nothing

In order:
1. Pull-ups off, or VPU floating (v3/v4).
2. The target has no power.
3. SDA and SCL swapped.
4. No common ground.
5. The device needs a moment after power-up: scan again.
6. The address is outside 0x08–0x77 (rare): scan a wider range.

## When a scan finds everything

Almost every address answering on a v3/v4 means SDA is held low, which reads as
an ACK: VPU floating, even on a bare bus with nothing wired. Turn the pull-ups off, or tie VPU
to a supply, and scan again.

## Board differences

- **BP6** reports one ACK or NACK for the whole transaction, not per byte. The
  app sends a STOP after any error so the bus is free.
- **Bit Pirate** checks the address with `ping`; later bytes of a write are
  not reported.
- **Sniffing:** wire SDA and SCL in parallel with the existing bus, share GND,
  leave power and pull-ups off if the bus has them. `+` = ACK, `-` = NACK.

Sources:
- docs/i2c.md
- docs/troubleshooting.md (I2C scan checks, AHT20 + BMP280, phantom addresses)
- docs/bus-pirate-6.md (pins, pull-ups)
- docs/bitpirate.md (dock pins, pull-ups, `[ ]` syntax, `ping`)
- docs/pins-and-power.md (VPU)
- buspirate/web/wiring.py (Seeed colours)
