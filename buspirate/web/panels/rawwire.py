"""Raw wire: bit-level control for buses that are nearly, but not quite, SPI."""

from __future__ import annotations

from ... import device as device_module

from ..registry import Action, Panel, Param, Wire, hexdump, keyvalue, text
from ..wiring import CABLE_CAVEAT, POWER_NOTE, colour

SPEED_CHOICES = [
    {"value": 0, "label": "5 kHz"},
    {"value": 1, "label": "50 kHz"},
    {"value": 2, "label": "100 kHz"},
    {"value": 3, "label": "400 kHz"},
]


def _configure(ctx, push_pull, three_wire, lsb_first, speed, power):
    ctx.mode.configure_peripherals(power=power)
    ctx.mode.set_speed(speed)
    ctx.mode.configure(push_pull=push_pull, three_wire=three_wire, lsb_first=lsb_first)
    return text(
        f"{'Three' if three_wire else 'Two'}-wire, "
        f"{'push-pull' if push_pull else 'open drain'}, "
        f"{'LSB' if lsb_first else 'MSB'} first.",
        tone="good",
    )


def _write(ctx, data, framed):
    if framed:
        ctx.mode.start_bit()
    ctx.mode.write(data)
    if framed:
        ctx.mode.stop_bit()
    return text(f"Clocked out {len(data)} byte(s).", tone="good")


def _read(ctx, count):
    return hexdump(ctx.mode.read(count), caption=f"{count} byte(s) clocked in")


def _write_read(ctx, data, count, use_cs):
    if use_cs:
        ctx.mode.cs_low()
    try:
        ctx.mode.write(data)
        reply = ctx.mode.read(count) if count else b""
    finally:
        if use_cs:
            ctx.mode.cs_high()
    return hexdump(reply, caption=f"{count} byte(s) after writing {len(data)}")


def _bit(ctx):
    return keyvalue(
        [
            ["Clocked bit", ctx.mode.read_bit()],
            ["Data pin now", ctx.mode.peek_input()],
        ]
    )


def _pins(ctx, clock_high, data_high, tick):
    ctx.mode.set_clock(clock_high)
    ctx.mode.set_data(data_high)
    if tick:
        ctx.mode.clock_tick()
    return text(
        f"Clock {'high' if clock_high else 'low'}, "
        f"data {'high' if data_high else 'low'}"
        + (", then one clock pulse." if tick else "."),
        tone="good",
    )


def _cs(ctx, low):
    (ctx.mode.cs_low if low else ctx.mode.cs_high)()
    return text(f"CS {'low' if low else 'high'}.", tone="good")


PANEL = Panel(
    id="rawwire",
    requires=device_module.CAP_RAWWIRE,
    doc="rawwire",
    refcard_rows=["supplies", "GND"],
    title="Raw wire",
    blurb="Drive the clock and data lines yourself, one bit at a time.",
    mode="rawwire",
    order=55,
    wiring=[
        Wire("CLK", colour("CLK"), "clock", "you control every edge"),
        Wire("MOSI", colour("MOSI"), "data out", "and data in on two-wire buses"),
        Wire("MISO", colour("MISO"), "data in", "three-wire buses only"),
        Wire("CS", colour("CS"), "chip select", "if the target has one"),
        Wire("GND", colour("GND"), "GND", "always connect this first"),
    ],
    notes=[
        "Use this when a chip is almost SPI or almost I2C but not quite: an "
        "odd number of clock cycles, a shared data line, or a protocol you "
        "are still working out.",
        "Nothing here knows about framing, so a wrong result is usually a "
        "wrong number of clock pulses rather than bad wiring.",
        "The Bus Pirate can also enter an OpenOCD JTAG mode, but its command "
        "set is defined only in the firmware source, so this tool does not "
        "drive it — point OpenOCD at the device itself. To poke at JTAG by "
        "hand, the reference card maps MOSI=TDI, CLK=TCK, MISO=TDO, CS=TMS, "
        "and you can clock them from here.",
        POWER_NOTE,
        CABLE_CAVEAT,
    ],
    actions=[
        Action(
            name="configure",
            label="Set the bus up",
            primary=True,
            params=[
                Param("push_pull", "bool", "Push-pull outputs", default=True),
                Param("three_wire", "bool", "Three-wire (separate data in)", default=False),
                Param("lsb_first", "bool", "Least significant bit first", default=False),
                Param("speed", "enum", "Clock", default=2, choices=SPEED_CHOICES),
                Param("power", "bool", "Power the target (3.3V + 5V)", default=False),
            ],
            handler=_configure,
        ),
        Action(
            name="write_read",
            label="Write then read",
            recipe=True,
            help="The usual shape of a transaction: clock some bytes out, then "
            "clock some in.",
            params=[
                Param("data", "bytes", "Bytes to send", default="9f"),
                Param("count", "int", "Bytes to read back", default=2, minimum=0, maximum=256),
                Param("use_cs", "bool", "Hold CS low for it", default=True),
            ],
            handler=_write_read,
        ),
        Action(
            name="write",
            label="Write bytes",
            params=[
                Param("data", "bytes", "Bytes", default="00"),
                Param("framed", "bool", "Wrap in start/stop bits", default=False),
            ],
            handler=_write,
        ),
        Action(
            name="read",
            label="Read bytes",
            params=[Param("count", "int", "Bytes", default=4, minimum=1, maximum=256)],
            handler=_read,
        ),
        Action(
            name="bit",
            label="Clock one bit",
            help="Reads a single bit, then shows the data pin without clocking.",
            handler=_bit,
        ),
        Action(
            name="pins",
            label="Set clock and data by hand",
            params=[
                Param("clock_high", "bool", "Clock high", default=False),
                Param("data_high", "bool", "Data high", default=False),
                Param("tick", "bool", "Then pulse the clock once", default=False),
            ],
            handler=_pins,
        ),
        Action(
            name="cs",
            label="Chip select",
            params=[Param("low", "bool", "Assert (low)", default=True)],
            handler=_cs,
        ),
    ],
)
