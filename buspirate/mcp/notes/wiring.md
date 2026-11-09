# Wiring: cable colours and the rules that always apply

Every wiring step names **both** the pin label and the wire colour, in the
colours of the connected board's own cable. The owner does the wiring.

## v3 / v4: the Seeed probe cable

| Pin | Signal | Colour | I2C | SPI | UART | 1-Wire |
|---|---|---|---|---|---|---|
| 1 | MISO | black | | MISO | RX (from target TX) | |
| 2 | CS | white | | CS | | |
| 3 | MOSI | grey | SDA | MOSI | TX (to target RX) | data |
| 4 | CLK | purple | SCL | CLK | | |
| 5 | AUX | blue | | | | |
| 6 | VPU | green | pull-up rail | | | |
| 7 | ADC | yellow | | | | |
| 8 | +5V | orange | | | | |
| 9 | +3.3V | red | | | | |
| 10 | GND | brown | | | | |

- CLK is **purple** (once wrongly recorded as pink). Grey is MOSI. On a
  MAX31855, CLK on the grey lead read all zeros.
- **SparkFun cables are usually the reverse order** and the v2go differs
  again. If the cable is not a Seeed one, go by the board's own `i`/pin
  legend, not by colour.
- The v4 header is a 2x6 (two extra AUX pins, terminal-only). Its silkscreen
  is printed on the underside and reads mirrored.

## BP6 (and BP5): the official probe cable

| Header | VOUT | IO0 | IO1 | IO2 | IO3 | IO4 | IO5 | IO6 | IO7 | GND |
|---|---|---|---|---|---|---|---|---|---|---|
| Colour | red | orange | yellow | green | blue | purple | brown | grey | white | black |

| Bus | Pins |
|---|---|
| I2C | SDA IO0, SCL IO1 |
| SPI | CLK IO6, MOSI IO7, MISO IO4, CS IO5 |
| UART | TX IO4, RX IO5 |
| 1-Wire | data IO0 |

On the official cable the colour is the **heat shrink** at the end (the
wires themselves are grey silicone). IO4 is the **sixth** pin, not the fourth (the header starts with VOUT). The
**heat-shrink label on the cable end is the authority**; the labels by the
connector do not line up exactly with the pins.

## Bit Pirate dock

The dock's 10-pin header follows the BP6 layout, so the same colours apply by
position. Owners colour their DuPont jumpers to match.

| Dock pin | VIO | IO15 | IO16 | IO17 | IO18 | IO10 | IO11 | IO12 | IO13 | GND |
|---|---|---|---|---|---|---|---|---|---|---|
| BP6 equivalent | VOUT | IO0 | IO1 | IO2 | IO3 | IO4 | IO5 | IO6 | IO7 | GND |
| Colour | red | orange | yellow | green | blue | purple | brown | grey | white | black |

The silkscreen runs GND at the top down to VIO; colours follow the signal,
not the position from the top. Buses on the dock: I2C SDA IO15, SCL IO16;
SPI MISO IO10, CS IO11, CLK IO12, MOSI IO13; UART TX IO10, RX IO11.

## Rules for every job

- **GND first, always**, and a shared ground between the Bus Pirate, the
  target and anything else on the bus. No common ground is a top reason for
  "nothing found".
- **UART: cross TX and RX.** Bus Pirate TX goes to the target's RX, and the
  target's TX to the Bus Pirate's RX. If you see nothing, swap these two first.
- **SPI flash: tie WP and HOLD high** (to the chip's VCC). Otherwise the chip
  may ignore you, or accept writes and silently drop them.
- **Pull-ups on v3/v4 need VPU.** Tie VPU (green) to the bus's logic rail,
  or on a v4 select the internal rail in software. VPU floating means the
  pull-ups do nothing. If the target board has its own pull-ups (most
  breakouts do), leave the Bus Pirate's off.
- BP6 pull-ups (10 kΩ) pull to VOUT: VOUT needs a voltage, either from the
  supply or the target's own rail.
- **Wire by function, not by colour.** A DS18B20 probe's yellow lead is data
  and goes to MOSI (grey on the Seeed cable); the Bus Pirate's yellow is the
  ADC.
- Connect only one supply wire to the target, and only if the Bus Pirate is
  powering it.
- A wire that "worked yesterday" can fail intermittently: swap the lead.

Sources:
- buspirate/web/wiring.py (Seeed colours, SparkFun warning)
- buspirate/boards/bp6.py (BP6_HEADER, BP6_CABLE), buspirate/boards/bitpirate.py (DOCK_HEADER)
- docs/official/cables/cables.md
- docs/i2c.md, docs/spi.md, docs/uart.md, docs/onewire.md
- docs/bus-pirate-6.md (pins, cable labels)
- docs/bus-pirate-v4.md (2x6 header)
- docs/bitpirate.md (dock pins)
- docs/troubleshooting.md (purple CLK, MAX31855, probe cable)
