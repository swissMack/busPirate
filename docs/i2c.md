# I2C

Two wires shared by many chips, each with a 7-bit address.

## Wiring

| Probe wire | Seeed colour | Target |
|-----------|--------------|--------|
| CLK | pink | SCL |
| MOSI | grey | SDA |
| GND | brown | GND — connect this first |
| VPU | green | the bus supply rail |
| +3.3V or +5V | red / orange | VCC, only if you are powering the target |

## Pull-ups, which is what usually goes wrong

I2C lines are open-drain: devices only pull *down*, so something must pull
*up*. The Bus Pirate has built-in pull-ups, but they pull up to **whatever
you feed the VPU pin**. Leave VPU floating and switching them on does
nothing at all.

- Target powered by the Bus Pirate: tie VPU to the same rail you are feeding
  the target.
- Target powered by itself: tie VPU to the target's supply.
- Bus Pirate v4: you can switch VPU to an internal rail in software instead —
  **Set the pull-up rail**. It refuses if a voltage is already on VPU, which
  is the protection working.

If the bus already has pull-ups fitted (most breakout boards have them),
leave the Bus Pirate's off.

## Addresses

Everything here takes the **7-bit** address — `0x50`, not `0xA0`. The
read/write bit is added for you. Scan results show both forms so you can
match whatever the datasheet uses.

## Typical session

```python
with bp.i2c() as i2c:
    i2c.configure_peripherals(power=True, pullups=True)
    i2c.set_speed(i2c.SPEED_100KHZ)

    print([hex(a) for a in i2c.scan()])

    # A register read: write the register number, repeated start, then read.
    print(i2c.read_register(0x68, 0x00, 7).hex(" "))

    i2c.write_register(0x68, 0x07, b"\x00")
```

## Speeds

| Index | Speed |
|-------|-------|
| 0 | 5 kHz |
| 1 | 50 kHz |
| 2 | 100 kHz — the usual choice |
| 3 | 400 kHz |

Firmware older than v4.2 has only indices 0 and 1 (5 kHz and 50 kHz). The
driver reads your firmware version and rejects the rest with a message
listing what you do have.

Long wires and weak pull-ups both slow the rising edge. If 400 kHz is flaky,
drop to 100 kHz before suspecting anything else.

## Two ways to read

- **`read_register()`** uses a repeated start. Correct on any firmware, and
  what you want almost always.
- **`write_then_read()`** hands the whole transaction to the firmware in one
  command, which is much faster for bulk reads. It needs firmware v5.1+, and
  it has **no repeated start** — it writes the exact bytes you give it, then
  reads. Build the address byte yourself with `buspirate.i2c.address_byte()`.

## Sniffing

**Sniff the bus** watches traffic between two other devices without driving
anything. Wire SDA and SCL in parallel with the existing bus and share the
ground; leave power and the pull-ups off if the bus already has them.

The stream is decoded as you watch: `START`, the bytes on the bus, `+` for
each ACK and `-` for each NACK, then `STOP`. That is usually enough to work
out a register map from a driver you cannot read.

## When a scan finds nothing

In the order worth checking:

1. Pull-ups off, or VPU floating.
2. The target has no power.
3. SDA and SCL swapped.
4. No common ground.
5. The device needs a moment after power-up — scan again.
6. The address is outside 0x08–0x77 (rare, but some chips use reserved ones;
   pass a wider range to `scan()`).
