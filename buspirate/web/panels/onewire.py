"""1-Wire: find devices on the bus and read DS18B20 temperatures."""

from __future__ import annotations

import time

from ...onewire import ROM_MATCH
from ..registry import Action, Panel, Param, Wire, hexdump, table, text
from ..wiring import CABLE_CAVEAT, colour

FAMILIES = {
    0x01: "DS1990A iButton",
    0x10: "DS18S20 thermometer",
    0x22: "DS1822 thermometer",
    0x26: "DS2438 battery monitor",
    0x28: "DS18B20 thermometer",
    0x29: "DS2408 I/O",
    0x2D: "DS2431 EEPROM",
    0x3B: "DS1825 thermometer",
}

CONVERT_T = 0x44
READ_SCRATCHPAD = 0xBE
THERMOMETERS = (0x10, 0x22, 0x28, 0x3B)


def _search(ctx, power, pullups):
    ctx.mode.configure_peripherals(power=power, pullups=pullups)
    roms = ctx.mode.search_rom()
    if not roms:
        return text(
            "Nothing found. 1-Wire needs a real pull-up: fit a 4k7 resistor "
            "from the data line to VCC — the Bus Pirate's own pull-ups are too "
            "weak on their own.",
            tone="warn",
        )
    return table(
        ["ROM address", "Family", "Device"],
        [
            [rom.hex(":"), f"0x{rom[0]:02X}", FAMILIES.get(rom[0], "unlisted")]
            for rom in roms
        ],
        caption=f"{len(roms)} device(s) on the bus",
    )


def _temperatures(ctx, power, pullups):
    ctx.mode.configure_peripherals(power=power, pullups=pullups)
    roms = [rom for rom in ctx.mode.search_rom() if rom[0] in THERMOMETERS]
    if not roms:
        return text("No thermometers found on the bus.", tone="warn")

    rows = []
    for index, rom in enumerate(roms):
        ctx.progress(index, len(roms), f"converting {rom.hex(':')}")
        ctx.mode.reset()
        ctx.mode.write(bytes([ROM_MATCH]) + rom + bytes([CONVERT_T]))
        time.sleep(0.8)  # a 12-bit conversion takes up to 750 ms
        ctx.mode.reset()
        ctx.mode.write(bytes([ROM_MATCH]) + rom + bytes([READ_SCRATCHPAD]))
        scratchpad = ctx.mode.read(9)
        raw = int.from_bytes(scratchpad[0:2], "little", signed=True)
        celsius = raw / 16.0
        rows.append([rom.hex(":"), f"{celsius:.2f}", f"{celsius * 9 / 5 + 32:.1f}"])
    ctx.progress(len(roms), len(roms), "done")
    return table(["ROM address", "°C", "°F"], rows, caption="DS18B20 family")


def _read_rom(ctx, power, pullups):
    ctx.mode.configure_peripherals(power=power, pullups=pullups)
    rom = ctx.mode.read_rom()
    return hexdump(rom, caption="ROM of the only device on the bus")


_BUS = [
    Param("power", "bool", "Power the target", default=True),
    Param("pullups", "bool", "Enable the on-board pull-ups", default=True),
]

PANEL = Panel(
    id="onewire",
    title="1-Wire",
    blurb="One data wire and a ground. Mostly temperature sensors.",
    mode="onewire",
    order=50,
    wiring=[
        Wire("MOSI", colour("MOSI"), "DQ", "the single data line"),
        Wire("GND", colour("GND"), "GND", "always connect this first"),
        Wire("+3.3V", colour("+3.3V"), "VDD", "or leave floating for parasite power"),
    ],
    notes=[
        "Fit a 4k7 pull-up from DQ to VCC. This is the single commonest reason "
        "a 1-Wire bus finds nothing.",
        "A DS18B20 needs up to 750 ms per conversion, so readings are not instant.",
        CABLE_CAVEAT,
    ],
    actions=[
        Action(
            name="search",
            label="Find devices",
            primary=True,
            recipe=True,
            params=list(_BUS),
            handler=_search,
        ),
        Action(
            name="temperatures",
            label="Read temperatures",
            recipe=True,
            long_running=True,
            help="Finds every DS18B20-family sensor and reads each one.",
            params=list(_BUS),
            handler=_temperatures,
        ),
        Action(
            name="read_rom",
            label="Read the ROM",
            help="Only valid with exactly one device on the bus.",
            params=list(_BUS),
            handler=_read_rom,
        ),
    ],
)
