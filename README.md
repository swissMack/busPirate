# busPirate

A Python driver, command line and web dashboard for the
[Bus Pirate](http://dangerousprototypes.com/docs/Bus_Pirate) v3 and v4 — I2C,
SPI, UART, 1-Wire and raw wire, over the binary protocol rather than by
scraping the device's terminal. It talks to chips, watches other people's
buses, and reads, erases and programmes SPI flash.

## Start here

Plug the Bus Pirate in and double-click **`bin/dashboard.command`**. It builds
its own Python environment the first time, then opens the dashboard in your
browser.

No hardware to hand? **`bin/demo.command`** runs the whole thing against a
simulated Bus Pirate.

**→ [The user guide](docs/user-guide.md) is the place to start**, especially
if it has been a while.

## The dashboard

```
┌──────────────────────────────────────────────┐
│ busPirate   [recipes…]    ● Bus Pirate v3 · i2c│
├────────────┬─────────────────────────────────┤
│ Connection │  I2C                            │
│ ▸ I2C      │  Wiring: CLK→SCL  MOSI→SDA …    │
│   SPI      │  ┌ Scan the bus ──────────────┐ │
│   UART     │  │ ☑Power ☑Pull-ups [100kHz]  │ │
│   1-Wire   │  │ 0x50 EEPROM   0x68 RTC     │ │
│   Pins     │  └────────────────────────────┘ │
├────────────┴─────────────────────────────────┤
│ 11:39:13 -> 02   <- 01   -> 10 a0   <- 01 00 │
└──────────────────────────────────────────────┘
```

Every panel shows a photograph of the board with the pins it needs ringed and
labelled — `CLK → SCL`, `MOSI → SDA` — above the Bus Pirate's own reference
cards with your bus marked on them, plus the warnings that matter for it. The full user guide is in the sidebar too, so you
never have to leave the page to look something up. One-click recipes cover the
jobs worth coming back for: scan a bus, read a 24Cxx, identify and dump SPI
flash, read DS18B20 temperatures, sniff traffic between two other devices.

## What it does

| | |
|---|---|
| **Talk** | I2C, SPI, UART, 1-Wire, raw wire — scan, read, write, read registers |
| **Watch** | passive I2C and SPI sniffers, a UART monitor and a voltage monitor, decoded live |
| **Programme** | SPI flash: identify, dump, erase by sector or whole chip, write from a file, verify |
| **Measure** | voltage on the ADC pin, frequency on AUX, PWM out, pins by hand |

## Command line

```bash
buspirate ports              # find it
buspirate ping               # what is it?
buspirate i2c-scan           # what is on the bus?
buspirate spi-id             # what is this flash chip?
buspirate dashboard --demo   # the UI, simulated
```

## Python

```python
from buspirate import BusPirate

with BusPirate("auto") as bp:
    print(bp.profile.describe())          # "Bus Pirate v3, firmware v6.1"
    with bp.i2c() as i2c:
        i2c.configure_peripherals(power=True, pullups=True)
        i2c.set_speed(i2c.SPEED_100KHZ)
        print([hex(a) for a in i2c.scan()])
        print(i2c.read_register(0x68, 0x00, 7).hex(" "))
```

Opening identifies the hardware and enters binary mode; closing resets the
device back to its terminal, so an interrupted script never strands it.

## Documentation

| | |
|---|---|
| [User guide](docs/user-guide.md) | start here |
| [macOS setup](docs/macos-setup.md) | drivers, ports, the venv, the launcher |
| [Dashboard](docs/dashboard.md) | every panel and recipe |
| [Command line](docs/cli.md) | every subcommand |
| [I2C](docs/i2c.md) · [SPI](docs/spi.md) · [UART](docs/uart.md) · [1-Wire](docs/onewire.md) · [Pins & power](docs/pins-and-power.md) | per protocol: wiring, examples, gotchas |
| [Bus Pirate v4](docs/bus-pirate-v4.md) | what differs from a v3 |
| [Troubleshooting](docs/troubleshooting.md) | when it does not work |
| [Protocol reference](docs/protocol-reference.md) | the binary command tables |
| [Extending](docs/extending.md) | add a protocol, end to end |

## Credits

The reference cards in the hook-up diagrams come from the Dangerous Prototypes
wiki (dangerousprototypes.com), used under CC BY-SA. The colour table and the
per-bus pin names in this project are read from those cards. The board
photograph's licence has not been established — see
`buspirate/web/static/img/CREDITS.md` before publishing this repository.

## Development

```bash
make setup    # .venv with everything
make test     # the suite — no hardware needed
make demo     # the dashboard against a simulated device
make ports    # list serial ports
```

`tests/fake_serial.py` emulates the firmware's state machine and raises on any
command it does not recognise, so driver bugs fail loudly instead of reading
zeros. The mode tests run twice, once as a v3 and once as a v4.

## Status

Written against the published protocol documentation and tested against a
simulated device: 238 Python tests plus a frontend test that drives the real
UI. It has **not yet been run against real hardware** — see the checklist at
the end of [troubleshooting](docs/troubleshooting.md) for what is worth
verifying the first time you plug one in, chiefly the SPI clock phase
mapping, a flash write round trip, and the sniffers.
