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

