# Bus Pirate 6

## Limits

- Supply (VOUT): 0.8–5.0 V, 300 mA rated, current limit 0–500 mA (recipes use 100 mA).
  **The owner caps it at 5 V**; nothing above that is ever planned.
- IO pins are buffered and work from 1.2 to 5 V, following VOUT.
- A trip cuts the supply and sets a flag; fix the fault, then plan again.
- **When this server exits, the board goes to HiZ:** supply and pull-ups off, so an
  LCD loses its text. Power never outlives the Claude Code session.

## Pin map (go by the heat-shrink labels on the cable ends)

| Pin | Wire | Used for |
|---|---|---|
| VOUT | red | supply out, or the target's own voltage in; feeds the pull-ups |
| IO0 | orange | I2C SDA, 1-Wire DQ, LED data |
| IO1 | yellow | I2C SCL, APA102 clock |
| IO2 | green | free |
| IO3 | blue | free |
| IO4 | purple | SPI MISO, UART TX (to the target's RX) |
| IO5 | brown | SPI CS, UART RX (from the target's TX); Microwire CS, active-high |
| IO6 | grey | SPI CLK |
| IO7 | white | SPI MOSI |
| GND | black | ground: connect it first |

## The pull-up rule

Every IO pin has a 10 kΩ pull-up, powered from VOUT. They only work when VOUT has a
voltage: our supply on, or the target's own supply wired to VOUT. I2C and 1-Wire need
them; a target-powered plan feeds them from the target through VOUT.

## Target power

`recipe_plan` measures first. A target that already has a voltage is *target-powered*:
our supply stays off and the measured voltage is used. A voltage outside the recipe's
range is refused.

## Risks (decided)

- SHT4x and anything with a lower hard maximum: the recipe caps the supply there.
- EEPROM, FRAM and flash erase or write (phase 2: `*-write` recipes, then `recipe_commit`):
  a separate yes naming the chip, address range and size; a backup is read to the owner's
  disk first unless the owner declines. A commit is reported as done only when the
  read-back matches; otherwise `committed` is false and the result names the backup.
- DDR4/DDR5 SPD: read only.
- SLE4442: read only; a passcode attempt needs its own yes, shows the attempts left,
  and is never retried automatically.
- USB-PD: requesting above 5 V needs its own yes naming the voltage.
- PS/2 and USB keyboard sniffers: `owner-only` — confirm the device is the owner's.
- UART glitching: its own yes; it is fault injection on the target.
- VPP SMPS: not automated.

`hiz` makes everything safe.

## Unverified on a real board

Built from the datasheets and the firmware source; all fakes pass. Check on hardware:

- SPI `chip_select_idle` (active-high CS for Microwire) is honoured over BPIO2.
- Microwire read alignment: one dummy bit is shifted out of the read.
- DDR4 page select by an address-only I2C write, and a 256-byte `read_after_write`.
- DS2431 copy-scratchpad without a strong pull-up.
- I2C EEPROM busy polling by an empty write needs a NACK from a real chip.
- The MOSI level the BP6 clocks during read-only SPI bytes (the Microwire ready poll).
- The BP6 keeps one 1-Wire transaction across separate reset, write and read requests.
