# Command line

```
buspirate ports [--all]
buspirate ping       [-p PORT] [-v]
buspirate i2c-scan   [-p PORT] [--speed 0..3] [--no-power] [--no-pullups]
buspirate spi-id     [-p PORT] [--speed 0..7]
buspirate dashboard  [--demo] [--variant v3|v4] [--no-browser]
```

`-p/--port` defaults to `auto`, which picks the most likely device.
`-v` logs every byte in both directions — the fastest way to see where a
transaction stops.

## `ports`

```console
$ buspirate ports
 * /dev/cu.usbserial-A700eEoR  [0403:6001]  - FTDI FT232R (Bus Pirate v3)
   /dev/cu.usbmodem1130  [1234:5678]  - USB serial adapter, unrecognised chip

* = looks like a Bus Pirate; --port auto will choose it.
```

Non-USB ports (Bluetooth pairings, the debug console) are hidden unless you
pass `--all`.

## `ping`

```console
$ buspirate ping
/dev/cu.usbserial-A700eEoR: Bus Pirate v3, firmware v6.1
  bitbang protocol BBIO1
  features: adc, frequency_count, pwm, self_test
```

Confirms the port, the hardware and what the firmware supports. Run this
first whenever something is odd.

## `i2c-scan`

```console
$ buspirate i2c-scan --speed 3
2 device(s):
  0x50  (write 0xA0 / read 0xA1)
  0x68  (write 0xD0 / read 0xD1)
```

Exits non-zero when nothing answers, so it works in a script.

## `spi-id`

```console
$ buspirate spi-id
JEDEC ID: ef 40 18
```

`ef` is Winbond; `18` means 2^24 bytes, so 16 MB.

## Scripting

The CLI covers the common cases; anything else is a few lines of Python.

```python
from buspirate import BusPirate

with BusPirate("auto") as bp:
    print(bp.profile.describe())
    with bp.i2c() as i2c:
        i2c.configure_peripherals(power=True, pullups=True)
        i2c.set_speed(i2c.SPEED_100KHZ)
        for address in i2c.scan():
            print(hex(address), i2c.read_register(address, 0x00, 4).hex(" "))
```

`BusPirate` resets the device back to its terminal on exit, so an interrupted
script never leaves the hardware in a strange state. See `examples/` for
runnable versions.
