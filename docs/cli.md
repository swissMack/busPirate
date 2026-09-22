# Command line

```
buspirate ports [--all]
buspirate ping       [-p PORT] [-v]
buspirate i2c-scan   [-p PORT] [--speed 0..3] [--no-power] [--no-pullups]
buspirate spi-id     [-p PORT] [--speed 0..7]
buspirate dashboard  [--demo] [--variant v3|v4] [--no-browser]
buspirate app        [--demo] [--variant v3|v4] [--port-number N]
```

`-p/--port` defaults to `auto`, which picks the most likely device.
`-v` logs every byte in both directions — the fastest way to see where a
transaction stops.

`dashboard` opens a browser tab; `app` opens the same UI in its own window.
See [Dashboard](dashboard.md#window-or-browser) for the difference.

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

## `app`

Opens the dashboard in its own window instead of a browser tab — same
server, same UI, nothing about a panel or a recipe behaves differently. See
[Dashboard](dashboard.md#window-or-browser) for the full story.

It needs one extra package on top of `[web]`:

```bash
pip install -e '.[app]'
```

Takes `--demo`, `--variant` and `--port-number`, the same as `dashboard`.
There is no `--host` or `--no-browser`: the window always binds loopback,
and there is no browser step to skip. Closing the window shuts down
cleanly — any running stream is stopped, the board is disconnected, and the
port is released before the process exits.

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
