"""1-Wire: find devices on the bus and read the ones the catalog knows."""

from __future__ import annotations

from ... import device as device_module
from ... import devices
from ..registry import Action, Panel, Param, Wire, hexdump, table, text
from ..wiring import CABLE_CAVEAT, POWER_NOTE, colour

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
            [rom.hex(":"), f"0x{rom[0]:02X}", devices.onewire_label(rom[0]) or "unlisted"]
            for rom in roms
        ],
        caption=f"{len(roms)} device(s) on the bus",
    )


def _read_sensors(ctx, power, pullups):
    ctx.mode.configure_peripherals(power=power, pullups=pullups)
    roms = ctx.mode.search_rom()
    known = [rom for rom in roms if devices.onewire_readable(rom[0])]
    if not known:
        found = f"{len(roms)} device(s) found, but none" if roms else "No devices found, so none"
        return text(f"{found} the app can read yet. Find devices lists what is there.",
                    tone="warn")
    rows = []
    for index, rom in enumerate(known):
        ctx.progress(index, len(known), f"measuring {rom.hex(':')}")
        reading = devices.read_onewire(ctx.mode, rom)
        rows.append([
            reading.where,
            reading.device,
            reading.raw.hex(" "),
            "; ".join(f"{k} {v}" for k, v in reading.meaning),
        ])
    ctx.progress(len(known), len(known), "done")
    return table(["ROM address", "Chip", "Raw bytes", "What it means"], rows,
                 caption=f"{len(known)} of {len(roms)} device(s) read")


def _read_rom(ctx, power, pullups):
    ctx.mode.configure_peripherals(power=power, pullups=pullups)
    rom = ctx.mode.read_rom()
    return hexdump(rom, caption="ROM of the only device on the bus")


_BUS = [
    Param("power", "bool", "Power the target (3.3V + 5V)", default=False),
    Param("pullups", "bool", "Enable the on-board pull-ups", default=False),
]

PANEL = Panel(
    id="onewire",
    requires=device_module.CAP_ONEWIRE,
    refcard_column='1-Wire',
    refcard_rows=['VPU', 'supplies', 'GND'],
    doc="onewire",
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
        POWER_NOTE,
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
            name="read_sensors",
            label="Read the sensors",
            recipe=True,
            long_running=True,
            help="Finds every device the app knows how to read, makes each "
            "measure, and shows its raw bytes with what they mean. Knows: "
            + ", ".join(d.name for d in devices.devices("onewire") if d.measure) + ".",
            params=list(_BUS),
            handler=_read_sensors,
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
