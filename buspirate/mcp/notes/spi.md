# SPI: four wires, flash chips and sensors

## Wiring

| Signal | v3/v4 (Seeed) | BP6 | Bit Pirate dock |
|---|---|---|---|
| CLK / SCK | CLK, purple | IO6, grey | IO12, grey |
| MOSI / DI | MOSI, grey | IO7, white | IO13, white |
| MISO / DO | MISO, black | IO4, purple | IO10, purple |
| CS / SS (active low) | CS, white | IO5, brown | IO11, brown |
| GND | brown | black | black |
| VCC | +3.3V, red | VOUT, red | VIO, red |

- **Serial flash: tie WP and HOLD high.** This catches people every time.
- Most serial flash is **3.3 V only**; 5 V destroys it. On a v3/v4 the
  choice is made by which supply wire you connect.
- MOSI is Bus Pirate out / chip in; MISO is chip out / Bus Pirate in.

## Identify first: JEDEC ID

Send `0x9F`, read 3 bytes.

| Byte | Meaning |
|---|---|
| 1 | manufacturer: `EF` Winbond, `C2` Macronix, `20` Micron, `BF` SST, `1F` Atmel |
| 2 | memory type |
| 3 | capacity as a power of two: `18` = 2^24 bytes = 16 MB |

## All `00` or all `FF`

**The chip is not blank.** It means:
- MISO is not connected, or
- WP/HOLD are not tied high, or
- CLK is on the wrong lead: an unclocked chip keeps sending its first bit, so
  a MAX31855 read `00 00 00 00` with CLK on grey instead of purple.

On a BP6, to tell a missing MISO from a missing clock: switch the pull-ups
on and read again. A MISO lead that goes nowhere then reads `ff ff ff ff`; a
chip that is powered but not clocked still reads zeros. The BP6 status lists
the voltage on every IO pin.

## Writing flash safely

1. **Dump first.** It is the only way back.
2. Programming only turns 1s into 0s, so erase to `0xFF` first.
3. Erase works in blocks (typically 4 KB sectors): it wipes the whole sector,
   including bytes outside the range you meant.
4. A page program must not cross a 256-byte page boundary; the chip wraps to
   the page start and silently corrupts. The driver splits on pages.
5. Verify after writing.

Writes that seem to do nothing: almost always **WP held low**. The commands
are accepted and silently ignored; the driver reads the status register back
and raises.

## Mode and speed

| Mode | Clock idles | Data sampled |
|---|---|---|
| 0 | low | rising edge (the usual one) |
| 1 | low | falling edge |
| 2 | high | falling edge |
| 3 | high | rising edge |

Nearly all serial flash is mode 0 (mode 3 also works). Data that looks
shifted by a bit means the wrong mode.

v3/v4 speeds: 30 kHz, 125 kHz, 250 kHz, 1 MHz, 2 MHz, 2.6 MHz, 4 MHz, 8 MHz.
Start at 1 MHz; above 2 MHz the wiring matters more than the chip. At 1 MHz
a dump runs at roughly 100 KB/s.

## Board differences

- **BP6:** all four modes. Transfers over 512 bytes are split with CS held
  low throughout. flashrom works through binmode 5 (see the avr note for the
  replug).
- **Bit Pirate:** mode 0 only; 1, 2, 4 or 8 MHz; flash read, dump and verify
  only (no write or erase from the driver). For writing, its USB flashrom
  `serprog` adapter: `flashrom -p serprog:dev=<port>:921600,spispeed=4M`.
- **v3/v4 flashrom:** `-p buspirate_spi:dev=<port>,spispeed=1M`.
- **BP6 flashrom (binmode 5):** `-p buspirate_spi:dev=<binary port>,serialspeed=115200,spispeed=1M`.
  The serial speed is fixed at 115200, and the port is the binary one, not the
  terminal.
- **Sniffing (v3/v4):** wire in parallel, share GND. Good to about 10 MHz; if
  it cannot keep up the firmware aborts and the MODE LED goes out.

Sources:
- docs/spi.md
- docs/troubleshooting.md (SPI all 00/FF, MAX31855, BP6 pull-up trick)
- docs/bus-pirate-6.md (pins)
- docs/bitpirate.md (SPI limits, dock pins)
- docs/bitpirate-wiki/99-adapters.md (serprog adapter)
- docs/official/software/flashrom.md
- buspirate/web/wiring.py (Seeed colours)
