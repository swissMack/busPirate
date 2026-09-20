# busPirate

A Python driver for the [Bus Pirate](http://dangerousprototypes.com/docs/Bus_Pirate)
v3/v4 **binary ("bitbang") protocol** — I2C, SPI, UART and 1-Wire from Python,
without scraping the device's human-readable terminal.

## Install

```bash
pip install -e ".[dev]"     # pyserial, plus pytest for the test suite
```

## Quick start

```python
from buspirate import BusPirate

with BusPirate("/dev/tty.usbserial-A700eEoR") as bp:
    with bp.i2c() as i2c:
        i2c.configure_peripherals(power=True, pullups=True)
        i2c.set_speed(i2c.SPEED_100KHZ)
        print([hex(a) for a in i2c.scan()])
        print(i2c.read_register(0x50, 0x00, 16).hex(" "))
```

`BusPirate.open()` knocks the device out of its terminal into binary mode;
closing it resets the device back to the terminal, so an interrupted script
never leaves the hardware in a strange state. Modes are exclusive — one at a
time, and `close()`/the `with` block returns to bitbang mode.

## Command line

```bash
python -m buspirate ping     -p /dev/tty.usbserial-A700eEoR
python -m buspirate i2c-scan -p /dev/tty.usbserial-A700eEoR --speed 3
python -m buspirate spi-id   -p /dev/tty.usbserial-A700eEoR
```

Add `-v` to log every byte in both directions — the fastest way to tell a
wiring fault from a protocol one.

## What each mode gives you

| Mode | Entry | Highlights |
|------|-------|-----------|
| I2C | `bp.i2c()` | `scan()`, `write()`, `read()`, `write_then_read()`, `read_register()`; 7-bit addresses, NACKs raise `NackError` |
| SPI | `bp.spi()` | `transfer()`, `write_then_read()`, `select()` context manager for CS, `set_mode(0-3)` |
| UART | `bp.uart()` | `set_baudrate()`, `configure()` framing, `write()`, echo-based receive |
| 1-Wire | `bp.onewire()` | `reset()`, `read()`/`write()`, `search_rom()` |

Raw pin control (`bp.set_pins`, `bp.set_pin_directions`) is available in
bitbang mode, before entering a protocol mode.

## Layout

| Path | Purpose |
|------|---------|
| `buspirate/` | The driver package — `base.py` is transport + bitbang, one module per mode |
| `examples/` | Runnable scripts: I2C scan, SPI flash dump, DS18B20 temperatures |
| `tests/` | Pytest suite driven by `tests/fake_serial.py`, a protocol-level fake — no hardware needed |
| `captures/` | Saved bus captures / logs (gitignored) |
| `docs/` | Pinouts, target notes, protocol cheatsheets |

## Tests

```bash
python -m pytest        # 32 tests, no hardware required
```

`tests/fake_serial.py` emulates the firmware's state machine and **raises on
any command it does not recognise**, so a driver bug shows up as a failure
rather than a silent read of zeros.

## Hardware notes

- The Bus Pirate's pull-ups are passive and weak. For I2C they are usually
  fine; for 1-Wire fit an external 4k7 to Vpu.
- `write_then_read` needs firmware v5.1 or newer, and caps both directions at
  4096 bytes.
- Nothing here targets hardware you don't own. Keep dumps and target
  credentials out of git — see `.gitignore`.
