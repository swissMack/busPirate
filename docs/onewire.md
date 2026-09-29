# 1-Wire

One data line plus ground. Mostly Dallas/Maxim temperature sensors and ID
chips.

## Wiring

| Probe wire | Seeed colour | Target |
|-----------|--------------|--------|
| MOSI | grey | DQ, the single data line |
| GND | brown | GND — connect this first |
| +3.3V | red | VDD, or leave floating for parasite power |

**Fit a 4k7 resistor from DQ to VCC.** The Bus Pirate's internal pull-ups are
too weak for 1-Wire on their own, and this is far and away the most common
reason a bus finds nothing.

## Finding devices

```python
with bp.onewire() as ow:
    ow.configure_peripherals(power=True, pullups=True)
    for rom in ow.search_rom():
        print(rom.hex(":"), hex(rom[0]))
```

The first byte is the family code:

| Code | Device |
|------|--------|
| `0x01` | DS1990A iButton |
| `0x10` | DS18S20 thermometer |
| `0x22` | DS1822 thermometer |
| `0x28` | DS18B20 thermometer — the common one |
| `0x2D` | DS2431 EEPROM |

`read_rom()` is shorter but only valid with exactly one device on the bus —
with several, they all answer at once and you get nonsense.

## Reading a DS18B20

```python
from buspirate.onewire import ROM_MATCH

ow.reset()
ow.write(bytes([ROM_MATCH]) + rom + bytes([0x44]))   # start conversion
time.sleep(0.8)                                       # up to 750 ms at 12 bits
ow.reset()
ow.write(bytes([ROM_MATCH]) + rom + bytes([0xBE]))   # read scratchpad
raw = int.from_bytes(ow.read(9)[0:2], "little", signed=True)
print(raw / 16.0, "°C")
```

The dashboard's **Read the sensors** does all of that for every sensor it
finds, checks the scratchpad's CRC, and uses each family's own formula: a
DS18S20 (family `0x10`) counts in half degrees, not sixteenths, so the
`raw / 16.0` above is only right for the DS18B20, DS1822 and DS1825.

## Gotchas

- The 750 ms conversion is real. Reading immediately gives you the previous
  value, or 85.0 °C — the power-on default, and a reliable sign the
  conversion never completed.
- Parasite power (no VDD wire) works, but needs a strong pull-up during
  conversion. If parasite-powered sensors read 85.0 °C, give them a VDD wire.
- Long runs of ordinary wire work surprisingly well; star topologies do not.
- **Search finds nothing and Read ROM returns all `00`:** the data line is
  stuck low, which almost always means no pull-up. Many DS18B20 probes and
  "modules" have no resistor, whatever the listing says: fit 4.7 kΩ from
  DQ to the supply. On a v4, ticking the on-board pull-ups does nothing
  unless VPU is wired to a supply.
- **Wire by function, not by colour.** A probe's yellow lead is data and
  goes to **MOSI** (grey on the Seeed cable); the Bus Pirate's yellow lead
  is the ADC. A probe's black goes to GND, not to a black MISO lead.
