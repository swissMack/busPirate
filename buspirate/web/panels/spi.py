"""SPI: identify and read serial flash, or talk to any SPI chip."""

from __future__ import annotations

import time

from ... import device as device_module
from ... import devices
from ...spi import SPI
from ...spiflash import SECTOR_SIZE, SPIFlash
from ..registry import Action, Panel, Param, Wire, hexdump, keyvalue, live, text, with_meaning
from ..wiring import CABLE_CAVEAT, POWER_NOTE, colour

CMD_JEDEC_ID = 0x9F
CMD_READ = 0x03

JEDEC_MANUFACTURERS = devices.JEDEC_MANUFACTURERS

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
    Param("power", "bool", "Power the target (3.3V + 5V)", default=False,
          requires=device_module.CAP_SUPPLIES),
    Param("speed", "enum", "Clock", default=3, choices=SPEED_CHOICES),
    Param("spi_mode", "enum", "SPI mode", default=0, choices=MODE_CHOICES,
          requires=device_module.CAP_SPI_MODES),
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


def _read_sensor(ctx, chip, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    reading = devices.spi_sensor(chip).measure(ctx.mode)
    return with_meaning(
        hexdump(reading.raw, caption=f"{reading.device}, {len(reading.raw)} byte(s)"),
        reading.meaning,
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
    flash = SPIFlash(ctx.mode)
    path = ctx.capture_path(filename)
    started = time.monotonic()
    done = 0
    with open(path, "wb") as handle:
        for chunk in flash.iter_read(0, length):
            handle.write(chunk)
            done += len(chunk)
            ctx.progress(done, length, f"read 0x{done:06X}")
    elapsed = time.monotonic() - started
    return text(f"Wrote {length} bytes to {path} in {elapsed:.1f}s.", tone="good")


def _flash_erase_sector(ctx, offset, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    flash = SPIFlash(ctx.mode)
    base = offset - (offset % SECTOR_SIZE)
    flash.erase_sector(base)
    return text(
        f"Erased the 4 KB sector at 0x{base:06X}. Every byte in it is now 0xFF.",
        tone="good",
    )


def _flash_erase_chip(ctx, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    started = time.monotonic()
    SPIFlash(ctx.mode).erase_chip()
    return text(
        f"The whole chip is erased, in {time.monotonic() - started:.1f}s.",
        tone="good",
    )


def _flash_write(ctx, filename, offset, verify, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    data = ctx.session.read_capture(filename)
    flash = SPIFlash(ctx.mode)
    started = time.monotonic()
    sectors = flash.erase_range(offset, len(data), ctx.progress)
    flash.write(offset, data, ctx.progress)
    message = (
        f"Erased {sectors} sector(s) and wrote {len(data)} bytes from "
        f"{filename} at 0x{offset:06X}"
    )
    if verify:
        bad = flash.verify(offset, data, ctx.progress)
        if bad is not None:
            return text(
                f"{message}, but it reads back wrong from 0x{bad:06X}. The chip "
                "may be write-protected — check that WP is tied high.",
                tone="warn",
            )
        message += ", verified"
    return text(f"{message}. {time.monotonic() - started:.1f}s.", tone="good")


def _flash_verify(ctx, filename, offset, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    data = ctx.session.read_capture(filename)
    bad = SPIFlash(ctx.mode).verify(offset, data, ctx.progress)
    if bad is None:
        return text(
            f"All {len(data)} bytes match {filename} from 0x{offset:06X}.",
            tone="good",
        )
    return text(f"First difference at 0x{bad:06X}.", tone="warn")


def _sniff(ctx, cs_low_only, power, speed, spi_mode):
    _setup(ctx, power, speed, spi_mode)
    ctx.mode.start_sniffer(cs_low_only=cs_low_only)
    return live(
        "SPI sniffer",
        decoder="spi-sniffer",
        caption="Watching another master talk to the chip. Nothing is driven.",
        warning="The sniffer is hardware and good to about 10 MHz. If it "
        "cannot keep up the firmware aborts the sniff and the MODE LED goes "
        "out.",
    )


PANEL = Panel(
    id="spi",
    refcard_column='SPI',
    refcard_rows=['supplies', 'GND'],
    doc="spi",
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
        "chip may never respond — and writes will fail silently if WP is low.",
        "Programming only turns 1s into 0s, so a region has to be erased back "
        "to 0xFF first. Erasing works in 4 KB sectors, never single bytes.",
        "A reply of all 0x00 or all 0xFF almost always means MISO is not "
        "connected, not that the chip is blank.",
        POWER_NOTE,
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
            name="read_sensor",
            label="Read a sensor",
            recipe=True,
            help="SPI has no addresses, so the app cannot find the chip: pick "
            "it, and it shows the raw bytes with what they mean.",
            params=[
                Param("chip", "enum", "Chip",
                      default=devices.spi_sensors()[0].name,
                      choices=[{"value": d.name, "label": f"{d.name} — {d.summary}"}
                               for d in devices.spi_sensors()]),
            ] + list(_SETUP),
            handler=_read_sensor,
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
            name="flash_write",
            requires=device_module.CAP_SPI_FLASH_PROGRAM,
            label="Write a file to flash",
            long_running=True,
            confirm="This erases the sectors it covers and reprogrammes them. "
            "Anything already in those sectors is gone. Continue?",
            help="Takes a file from captures/. Erases the 4 KB sectors the "
            "range touches — including any part of them outside your range — "
            "then programmes and reads it back.",
            params=[
                Param("filename", "filename", "File in captures/", default="flash.bin"),
                Param("offset", "int", "Write at address", default=0, minimum=0),
                Param("verify", "bool", "Read back and check", default=True),
            ]
            + list(_SETUP),
            handler=_flash_write,
        ),
        Action(
            name="flash_verify",
            label="Compare with a file",
            long_running=True,
            help="Reads the chip and reports the first byte that differs.",
            params=[
                Param("filename", "filename", "File in captures/", default="flash.bin"),
                Param("offset", "int", "Start address", default=0, minimum=0),
            ]
            + list(_SETUP),
            handler=_flash_verify,
        ),
        Action(
            name="flash_erase_sector",
            requires=device_module.CAP_SPI_FLASH_PROGRAM,
            label="Erase one sector",
            confirm="Erasing cannot be undone. Continue?",
            help="Clears the 4 KB sector containing the address you give.",
            params=[Param("offset", "hex", "Address in the sector", default=0, minimum=0)]
            + list(_SETUP),
            handler=_flash_erase_sector,
        ),
        Action(
            name="flash_erase_chip",
            requires=device_module.CAP_SPI_FLASH_PROGRAM,
            label="Erase the whole chip",
            confirm="This erases every byte on the chip and cannot be undone. "
            "Dump it first if you might want it back. Continue?",
            long_running=True,
            help="Can take a minute or more on a large part.",
            params=list(_SETUP),
            handler=_flash_erase_chip,
        ),
        Action(
            name="sniff",
            label="Sniff the bus",
            recipe=True,
            stream=True,
            requires=device_module.CAP_SNIFFER,
            help="Passively watch an existing master and chip. Wire CLK, MOSI, "
            "MISO and CS in parallel with them and share the ground.",
            params=[
                Param(
                    "cs_low_only",
                    "bool",
                    "Only while CS is low",
                    default=True,
                    help="Filters out the idle chatter between transactions.",
                )
            ]
            + list(_SETUP),
            handler=_sniff,
        ),
        Action(
            name="configure",
            label="Set clock and mode",
            params=list(_SETUP),
            handler=_configure,
        ),
    ],
)
