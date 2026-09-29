# Extending

The dashboard is declarative. A panel describes its actions, their parameters
and its wiring; the frontend renders forms and results from that description.
**Adding a protocol is one driver module and one panel module, and no
JavaScript.**

## 1. A mode in the driver

```python
# buspirate/mybus.py
from .mode import Mode

class MyBus(Mode):
    enter_command = 0x05          # the bitbang byte that selects the mode
    banner_prefix = "RAW"         # without the trailing version digit
    title = "My bus"

    def ping(self, address: int) -> bytes:
        self._check_active()
        self.bp.write(bytes([0x02, address]))
        return self.bp.read(4)
```

`Mode` gives you `enter()`, `close()`, the context manager,
`configure_peripherals()`, `_write_bulk_chunks()` for payloads longer than
16 bytes, and `_check_active()`.

Expose it on the device:

```python
# buspirate/base.py
def mybus(self):
    from .mybus import MyBus
    return self._enter_mode(MyBus)
```

## 2. A panel

Any module in `buspirate/web/panels/` that exports `PANEL` becomes a tab.

```python
# buspirate/web/panels/mybus.py
from ..registry import Action, Panel, Param, Wire, hexdump, text
from ..wiring import CABLE_CAVEAT, POWER_NOTE, colour


def _ping(ctx, address):
    return hexdump(ctx.mode.ping(address), caption=f"reply from {address:#04x}")


PANEL = Panel(
    id="mybus",
    title="My bus",
    blurb="One line saying what this panel is for.",
    mode="mybus",                       # the BusPirate method that enters it
    order=45,                           # position in the sidebar
    wiring=[
        Wire("CLK", colour("CLK"), "SCK", "clock"),
        Wire("GND", colour("GND"), "GND", "always connect this first"),
    ],
    notes=[POWER_NOTE, CABLE_CAVEAT],
    actions=[
        Action(
            name="ping",
            label="Ping a device",
            primary=True,
            recipe=True,                # also appears in the one-click strip
            help="Shown under the button.",
            params=[Param("address", "hex", "Address", default=0x10)],
            handler=_ping,
        ),
    ],
)
```

That is the whole change. Restart the dashboard and the tab is there.

## Adding a device

Chips live in the **device catalog**, `buspirate/devices/`: one small module
per chip (or family), each describing a `Device`. The panels ask the catalog,
so adding a chip needs **no panel code and no JavaScript**. Pick the level you
need:

| You want | Do this |
|---|---|
| The chip **named** in I2C scan or 1-Wire search results | One line in `buspirate/devices/names.py` |
| An SPI flash **maker** named by Identify the chip | One line in `JEDEC_MANUFACTURERS`, same file |
| Its readings **translated** into real units | A module of its own — below |

### A translated chip, in four steps

1. **Copy the closest example** in `buspirate/devices/`:

   | Example | Copy it for |
   |---|---|
   | `aht20.py` | an I2C chip with a fixed address: send a command, read the reply |
   | `bmp280.py` | an I2C chip that shares its address (confirmed by an ID register), or needs calibration data |
   | `ds18x20.py` | 1-Wire: recognised by the family code, the ROM's first byte |
   | `max31855.py` | SPI: no addresses, so the user picks the chip from a list |
   | `ad595.py` | analog: a voltage on the ADC lead, translated by `from_volts` |
   | `hd44780.py` | an output device: text in, hex out (`compose`, `script`, `send`) |

2. **Change the facts** from the datasheet: address or family code, the
   "measure" command, how long to wait, and the formula in `decode()`.
   `decode()` returns label/value pairs — `[("Temperature", "29.07 °C")]` —
   and should say so plainly when the bytes cannot be right (a busy flag, a
   bad checksum, a power-on value).

3. **Register it**: add the module to `_MODULES` in
   `buspirate/devices/__init__.py`. Modules are listed by hand so the built
   app can never leave one out; a test fails if you forget.

4. **Test it against the datasheet.** Most datasheets print worked examples —
   raw bytes and the temperature they mean. Put those in
   `tests/test_devices.py`, as the existing chips do. When it has worked on a
   real board, set `verified=True`.

A minimal I2C sensor:

```python
# buspirate/devices/mychip.py
import time

from . import Device, Meaning, Reading

ADDRESS = 0x44


def decode(raw: bytes) -> Meaning:
    celsius = int.from_bytes(raw[0:2], "big") * 175 / 65535 - 45
    return [("Temperature", f"{celsius:.2f} °C")]


def measure(i2c, address: int) -> Reading:
    i2c.write(address, bytes([0x24, 0x00]))   # "measure now"
    time.sleep(0.02)
    raw = i2c.read(address, 6)
    return Reading("MYCHIP", f"0x{address:02X}", raw, decode(raw))


DEVICES = [
    Device("MYCHIP", "i2c", "temperature", addresses=(ADDRESS,),
           measure=measure,
           explain_read=lambda address, data: decode(data)),
]
```

What each `Device` field is for:

| Field | Bus | Used for |
|---|---|---|
| `addresses` | I2C | where it can live; also names it in scan results |
| `families` | 1-Wire | its family code(s) |
| `probe(i2c, address)` | I2C | telling it apart from other chips at a shared address |
| `measure(...)` | all | **Read the sensors** / **Read a sensor**: make it measure, return a `Reading` |
| `explain_read(address, data)` | I2C | the "What it means" box under a hand-made **Read bytes** |
| `explain_register(i2c, address, register, data)` | I2C | the same under **Read a register**; may read calibration, never starts a measurement |
| `from_volts(volts)` | analog | the **Translate as** choice on **Measure a voltage** |
| `verified` | all | `True` once it has worked on real hardware |

Use the bus methods every board has: `read`, `write` and `read_register` for
I2C (the Bit Pirate has no `write_register`); `reset`, `write` and `read` for
1-Wire; `write_then_read` for SPI.

## Parameters

| Type | Renders as | Accepts |
|------|-----------|---------|
| `int` | number box | `42`, `0x2a` |
| `hex` | number box, hex by default | `50`, `0x50` both mean 0x50 |
| `bytes` | text box | `de ad be ef`, `DEADBEEF`, `0xDE, 0xAD`, `de:ad` |
| `bool` | checkbox | |
| `enum` | dropdown — needs `choices=[{"value":…, "label":…}]` | |
| `text` | text box | |
| `filename` | text box, forced into `captures/` | |

`minimum` and `maximum` are enforced server-side, with a message naming the
field.

## Results

Return one of these from a handler; the frontend knows how to draw each.

| Helper | Shows |
|--------|-------|
| `text(msg, tone="info"/"good"/"warn")` | a sentence |
| `hexdump(data, start=0)` | hex and ASCII |
| `table(columns, rows)` | a table |
| `chips(items)` | small labelled tiles, as the I2C scan uses |
| `keyvalue(pairs)` | a two-column summary |
| `pins(state)` | pin tiles |

## The action context

`ctx.bp` is the `BusPirate`, `ctx.mode` the mode object (already entered),
`ctx.profile` the device profile. `ctx.progress(done, total, msg)` drives the
progress bar over the websocket, and `ctx.capture_path(name)` returns a safe
path under `captures/`.

## Capability gating

```python
Action(..., requires=device_module.CAP_PULLUP_VOLTAGE)
```

The action is hidden on hardware that lacks the capability, and the driver
raises `UnsupportedFeatureError` if called anyway. Capabilities are defined
in `buspirate/device.py`.

## Testing without hardware

`buspirate/simulator.py` (re-exported as `tests/fake_serial.py`) emulates the firmware's state machine and **raises on
any command it does not recognise** — so a new mode needs a matching
`_state_<name>` handler, and a driver bug shows up as a failure rather than a
silent read of zeros. Add your mode there, and the dashboard tests in
`tests/test_dashboard.py` will exercise your panel through the real HTTP API.

```bash
make test
make demo     # drive the new panel by hand, no hardware
```

## A board that is not a Bus Pirate

The ESP32 Bit Pirate shows how a different board fits in without the panels
learning about it:

- **A driver with the same surface.** `buspirate/bitpirate/` offers the calls
  the panels make, `i2c()`, `scan()`, `write_then_read()` and so on, on top of
  a different protocol.
- **Chosen before the first byte.** `buspirate/connect.py` picks the driver
  from the USB ID.
- **Capabilities hide what it cannot do.** `Panel.requires`, `Action.requires`
  and `Param.requires` name a capability, and `server._panels_json` drops
  whatever the connected board's profile lacks.
- **The board replaces wording, not code.** An entry in
  `web/wiring.py` `BOARDS` can carry `"panels"`, which swaps a panel's wiring,
  notes and action text for that board.

