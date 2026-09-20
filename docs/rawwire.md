# Raw wire

For buses that are nearly SPI or nearly I2C, and for protocols you are still
working out. Nothing here knows about framing: you drive the clock and the
data lines, one bit at a time if you want.

## Wiring

| Probe wire | Seeed colour | Target |
|-----------|--------------|--------|
| CLK | pink | clock — you control every edge |
| MOSI | grey | data out, and data in on a two-wire bus |
| MISO | black | data in, three-wire buses only |
| CS | white | chip select, if the target has one |
| GND | brown | GND — connect this first |

Open-drain output needs external pull-ups; push-pull does not.

## When to reach for it

- A chip that clocks an odd number of bits, so SPI's byte framing does not fit.
- A single bidirectional data line that is not I2C.
- Something undocumented, where you want to wiggle pins and watch.
- Bit-banging JTAG by hand (see below).

## Using it

```python
with bp.rawwire() as raw:
    raw.configure(push_pull=True, three_wire=False, lsb_first=False)
    raw.set_speed(raw.SPEED_100KHZ)

    raw.cs_low()
    raw.write(b"\x9f")
    print(raw.read(3).hex(" "))
    raw.cs_high()
```

Bit-level control, when bytes are the wrong unit:

```python
raw.set_clock(False)
raw.set_data(True)
raw.clock_tick()          # one pulse
print(raw.read_bit())     # clock in a single bit
print(raw.peek_input())   # read the pin without clocking
```

`start_bit()` and `stop_bit()` emit I2C-style framing if your target wants it.

## JTAG

The Bus Pirate has an OpenOCD JTAG mode (bitbang command `0b00000110`), but
its command set is documented only in the firmware source, so **this tool does
not drive it**. Point OpenOCD at the Bus Pirate directly instead.

To poke at a JTAG chain by hand, the reference card gives the mapping, and you
can clock these from the raw-wire panel:

| Probe wire | JTAG |
|-----------|------|
| MOSI | TDI |
| CLK | TCK |
| MISO | TDO |
| CS | TMS |

That is enough to shift an IR and read an IDCODE, which is usually all you
want before deciding whether a chain is alive.

## Gotchas

- A wrong result here is nearly always the wrong *number of clock pulses*,
  not bad wiring. Count them.
- `lsb_first` changes how bytes are shifted, not how they are displayed.
- Three-wire mode uses MISO for input; two-wire shares MOSI in both
  directions, so the target must release the line before you read.
