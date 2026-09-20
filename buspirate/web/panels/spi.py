"""SPI: identify and read serial flash, or talk to any SPI chip."""

from __future__ import annotations

import time

from ...spi import SPI
from ..registry import Action, Panel, Param, Wire, hexdump, keyvalue, text
from ..wiring import CABLE_CAVEAT, colour

CMD_JEDEC_ID = 0x9F
CMD_READ = 0x03

JEDEC_MANUFACTURERS = {
    0x01: "Spansion / Cypress",
    0x1F: "Atmel / Adesto",
    0x20: "Micron / ST",
    0x37: "AMIC",
    0x9D: "ISSI",
    0xBF: "SST / Microchip",
    0xC2: "Macronix",
    0xC8: "GigaDevice",
    0xEF: "Winbond",
}

SPEED_CHOICES = [
    {"value": 0, "label": "30 kHz"},
    {"value": 1, "label": "125 kHz"},
    {"value": 2, "label": "250 kHz"},
    {"value": 3, "label": "1 MHz (usual)"},
    {"value": 4, "label": "2 MHz"},
    {"value": 5, "label": "2.6 MHz"},
    {"value": 6, "label": "4 MHz"},
    {"value": 7, "label": "8 MHz"},
]

MODE_CHOICES = [
    {"value": 0, "label": "Mode 0 — idle low, sample rising (usual)"},
    {"value": 1, "label": "Mode 1 — idle low, sample falling"},
    {"value": 2, "label": "Mode 2 — idle high, sample falling"},
    {"value": 3, "label": "Mode 3 — idle high, sample rising"},
]

_SETUP = [
    Param("power", "bool", "Power the target from the Bus Pirate", default=True),
    Param("speed", "enum", "Clock", default=3, choices=SPEED_CHOICES),
    Param("spi_mode", "enum", "SPI mode", default=0, choices=MODE_CHOICES),
]


def _setup(ctx, power, speed, spi_mode):
    ctx.mode.configure_peripherals(power=power)
    ctx.mode.set_speed(speed)
    ctx.mode.set_mode(spi_mode)


def _configure(ctx, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    return text("SPI configured.", tone="good")


def _capacity(code: int) -> str:
    # Nearly every serial flash encodes capacity as log2(bytes) in byte 3.
    if 0x10 <= code <= 0x2A:
        size = 1 << code
        return f"{size // 1024} KB" if size < 1 << 20 else f"{size >> 20} MB"
    return "unknown"


def _jedec_id(ctx, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    jedec = ctx.mode.write_then_read(bytes([CMD_JEDEC_ID]), 3)
    if jedec in (b"\x00\x00\x00", b"\xff\xff\xff"):
        return text(
            f"Got {jedec.hex(' ')} back, which means nothing is driving MISO. "
            "Check MISO, CS and that the chip has power.",
            tone="warn",
        )
    return keyvalue(
        [
            ["Raw ID", jedec.hex(" ")],
            ["Manufacturer", JEDEC_MANUFACTURERS.get(jedec[0], f"0x{jedec[0]:02X}, unlisted")],
            ["Memory type", f"0x{jedec[1]:02X}"],
            ["Capacity", _capacity(jedec[2])],
        ],
        caption="JEDEC ID (command 0x9F)",
    )


def _transfer(ctx, data, read_count, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    reply = ctx.mode.write_then_read(data, read_count)
    return hexdump(reply, caption=f"{read_count} byte(s) clocked in after the write")


def _flash_read(ctx, offset, length, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    command = bytes([CMD_READ, (offset >> 16) & 0xFF, (offset >> 8) & 0xFF, offset & 0xFF])
    data = ctx.mode.write_then_read(command, length)
    return hexdump(data, start=offset, caption=f"flash read from 0x{offset:06X}")


def _flash_dump(ctx, length, filename, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    chunk_size = 1024
    path = ctx.capture_path(filename)
    started = time.monotonic()
    with open(path, "wb") as handle:
        for offset in range(0, length, chunk_size):
            size = min(chunk_size, length - offset)
            command = bytes(
                [CMD_READ, (offset >> 16) & 0xFF, (offset >> 8) & 0xFF, offset & 0xFF]
            )
            handle.write(ctx.mode.write_then_read(command, size))
            ctx.progress(offset + size, length, f"read 0x{offset + size:06X}")
    elapsed = time.monotonic() - started
    return text(
        f"Wrote {length} bytes to {path} in {elapsed:.1f}s.", tone="good"
    )


PANEL = Panel(
    id="spi",
    title="SPI",
    blurb="Four wires, one chip at a time. Start with the JEDEC ID.",
    mode="spi",
    order=30,
    wiring=[
        Wire("CLK", colour("CLK"), "SCK / CLK", "clock"),
        Wire("MOSI", colour("MOSI"), "DI / MOSI", "Bus Pirate out, chip in"),
        Wire("MISO", colour("MISO"), "DO / MISO", "chip out, Bus Pirate in"),
        Wire("CS", colour("CS"), "CS / SS", "active low"),
        Wire("GND", colour("GND"), "GND", "always connect this first"),
        Wire("+3.3V", colour("+3.3V"), "VCC", "most serial flash is 3.3V only"),
    ],
    notes=[
        "Serial flash chips also have WP and HOLD pins. Tie both high, or the "
        "chip may never respond.",
        "A reply of all 0x00 or all 0xFF almost always means MISO is not "
        "connected, not that the chip is blank.",
        CABLE_CAVEAT,
    ],
    actions=[
        Action(
            name="jedec_id",
            label="Identify the chip",
            primary=True,
            recipe=True,
            help="Sends 0x9F and decodes the manufacturer and capacity.",
            params=list(_SETUP),
            handler=_jedec_id,
        ),
        Action(
            name="flash_read",
            label="Read from flash",
            recipe=True,
            help="Standard 0x03 read with a 24-bit address.",
            params=[
                Param("offset", "int", "Start address", default=0, minimum=0),
                Param("length", "int", "Bytes", default=256, minimum=1, maximum=4096),
            ]
            + list(_SETUP),
            handler=_flash_read,
        ),
        Action(
            name="flash_dump",
            label="Dump flash to a file",
            recipe=True,
            long_running=True,
            help="Reads in 1 KB chunks into captures/. A 1 MB chip at 1 MHz "
            "takes a couple of minutes.",
            params=[
                Param(
                    "length",
                    "int",
                    "Bytes to dump",
                    default=65536,
                    minimum=1,
                    maximum=16 * 1024 * 1024,
                ),
                Param("filename", "filename", "Save as", default="flash.bin"),
            ]
            + list(_SETUP),
            handler=_flash_dump,
        ),
        Action(
            name="transfer",
            label="Send bytes",
            help="Writes your bytes with CS held low, then clocks in a reply.",
            params=[
                Param("data", "bytes", "Bytes to send", default="9f"),
                Param("read_count", "int", "Bytes to read back", default=3, minimum=0, maximum=4096),
            ]
            + list(_SETUP),
            handler=_transfer,
        ),
        Action(
            name="configure",
            label="Set clock and mode",
            params=list(_SETUP),
            handler=_configure,
        ),
    ],
)
