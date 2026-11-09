# 1-Wire: one data line plus ground

Mostly Dallas/Maxim temperature sensors (DS18B20) and ID chips.

## Wiring

| Signal | v3/v4 (Seeed) | BP6 | Bit Pirate dock |
|---|---|---|---|
| DQ (data) | MOSI, grey | IO0, orange | IO15, orange |
| GND | brown | black | black |
| VDD | +3.3V, red (or none for parasite power) | VOUT, red | VIO, red |

**Fit a 4.7 kΩ resistor from DQ to VCC.** The Bus Pirate's internal pull-ups
are too weak on their own, and this is far the most common reason a bus
finds nothing. Many DS18B20 probes and "modules" have no resistor, whatever
the listing says. On a v4, the on-board pull-ups do nothing unless VPU is
wired to a supply.

**Wire by function, not by colour.** A probe's yellow lead is data and goes to
MOSI (grey on the Seeed cable); the Bus Pirate's yellow lead is the ADC. The
probe's black goes to GND, not to the black MISO lead.

## Family codes (first ROM byte)

| Code | Device |
|---|---|
| `0x01` | DS1990A iButton |
| `0x10` | DS18S20 thermometer (counts in half degrees) |
| `0x22` | DS1822 thermometer |
| `0x28` | DS18B20 thermometer, the common one |
| `0x2D` | DS2431 EEPROM |

`read_rom()` is valid only with exactly one device on the bus.

## Reading a DS18B20

Reset, match ROM, `0x44` (convert), wait **750 ms** at 12 bits, reset, match
ROM, `0xBE` (read scratchpad), check the CRC. The raw value / 16 is °C for
the DS18B20, DS1822 and DS1825; a DS18S20 counts in half degrees.

## Symptoms

| What you see | What it means |
|---|---|
| Search finds nothing, Read ROM gives all `00` | data line stuck low: no pull-up |
| Exactly 85.0 °C | power-on default: the conversion never completed. Wait the full 750 ms, or give a parasite-powered sensor a real VDD wire |
| Parasite-powered sensors read 85.0 °C | they need a strong pull-up during conversion; wire VDD |
| Works on a line, fails on a star | star topologies do not work well |

## Board differences

- **v3/v4:** search returns `01`, then 8 bytes per device, then eight `FF`.
  Verified on a v4 with a DS18B20 and an external 4.7 kΩ.
- **BP6:** data on IO0, pull-ups on. Its binary interface works in whole
  bytes, so Find devices reads the **one** device on the bus. With several,
  type `m 1wire` then `scan` in the terminal. Verified with a DS18B20 and an
  external 4.7 kΩ to VOUT.
- **Bit Pirate:** data on IO15 on the dock (unverified on hardware).

Sources:
- docs/onewire.md
- docs/troubleshooting.md (1-Wire finds nothing, 85.0 °C, v4 and BP6 checks)
- docs/bus-pirate-6.md (1-Wire limits)
- docs/bitpirate.md (1-Wire on IO15)
- buspirate/web/wiring.py (Seeed colours)
