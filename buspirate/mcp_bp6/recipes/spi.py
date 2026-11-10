"""SPI recipes: a flash chip (identify, optional read-only backup) and the MAX31855.

``check`` and ``action`` get only the board and the merged options. They enter
SPI mode (mode 0, up to 1 MHz) and close it again; they never touch the supply
or the pull-ups, which the engine has already set.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ... import devices
from ...mcp import jobs
from ...spiflash import SPIFlash
from .. import backup
from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
BLANK = (b"\x00\x00\x00", b"\xff\xff\xff")
SPI_WIRING = (("CLK", "IO6"), ("MOSI / DI", "IO7"), ("MISO / DO", "IO4"), ("CS", "IO5"),
              ("GND", "GND"), ("VCC", "VOUT"))
Options = Dict[str, Any]


def open_spi(bp: Any, khz: int = 1000):
    """Enter SPI mode 0 at the fastest speed not above ``khz``. Close it when done."""
    m = bp.spi()
    try:
        m.set_speed(jobs._pick(jobs._spi_speeds(bp), khz * 1000))
        m.set_mode(0)
    except BaseException:
        m.close()
        raise
    return m


def describe_jedec(jedec: bytes) -> Dict[str, Any]:
    """The JEDEC ID in words; a blank ID names nothing and carries the warning."""
    blank = jedec in BLANK
    maker = devices.JEDEC_MANUFACTURERS.get(jedec[0], "unlisted maker 0x%02X" % jedec[0])
    code = jedec[2]
    return {
        "jedec": jedec.hex(" "),
        "manufacturer": None if blank else "%s, memory type 0x%02X" % (maker, jedec[1]),
        "capacity_bytes": None if blank or not 0x10 <= code <= 0x2A else 1 << code,
        "warning": jobs.NOT_BLANK_WARNING if blank else None,
    }


# -- flash --------------------------------------------------------------------------

def _length(opts: Options) -> Optional[int]:
    length = opts.get("length")
    if length is None:
        return None
    if isinstance(length, bool) or not isinstance(length, int) or length < 1:
        raise ValueError("length must be a whole number of bytes, 1 or more, not %r" % (length,))
    return length


def _flash_check(bp: Any, opts: Options) -> Dict[str, Any]:
    try:
        length = _length(opts)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    with open_spi(bp) as m:
        info = describe_jedec(SPIFlash(m).jedec_id())
    if info["warning"]:
        return {"ok": False, "error": "no flash chip answers (JEDEC ID %s)" % info["jedec"],
                "hint": info["warning"]}
    size = info["capacity_bytes"]
    if opts.get("backup") and size is None and length is None:
        return {"ok": False, "error": "the JEDEC ID does not give the chip's size: pass length",
                "jedec": info["jedec"]}
    if length is not None and size is not None and length > size:
        return {"ok": False, "error": "length %d is more than the chip's %d bytes"
                % (length, size)}
    return {"ok": True, "jedec": info["jedec"]}


def _flash_action(bp: Any, opts: Options) -> Dict[str, Any]:
    """Name the flash chip; with backup=True also read it (all, or length bytes) to a file."""
    with open_spi(bp) as m:
        flash = SPIFlash(m)
        info = describe_jedec(flash.jedec_id())
        if not opts.get("backup"):
            return info
        total = _length(opts) or info["capacity_bytes"]
        data = b"".join(flash.iter_read(0, total))
    saved = backup.save(data, "spi-flash-" + info["jedec"].replace(" ", ""))
    saved.update(jedec=info["jedec"], manufacturer=info["manufacturer"],
                 capacity_bytes=info["capacity_bytes"], first_64_hex=data[:64].hex(" "))
    return saved


register(Recipe(
    name="spi-flash", title="SPI flash chip: identify it and optionally back it up",
    words=("spi-flash", "flash", "spi", "25q", "w25q", "winbond", "jedec", "bios", "firmware",
           "backup", "dump", "memory"),
    bus="spi", default_mv=3300, min_mv=1800, max_mv=3600, pullups=False, wiring=SPI_WIRING,
    check=_flash_check, action=_flash_action, options={"backup": False, "length": None},
    source=DOCS + "devices/w25q64/",
    notes=("reading is harmless, but a chip soldered on a board may share its bus: power the "
           "board off and keep its other devices quiet",
           "backup=True reads the whole chip; length limits it")))


# -- MAX31855 -----------------------------------------------------------------------

def _max31855_action(bp: Any, opts: Options) -> Dict[str, Any]:
    """Read the thermocouple temperature from the MAX31855."""
    device = devices.spi_sensor("MAX31855")
    with open_spi(bp) as m:
        reading = device.measure(m)
    return {"device": reading.device, "values": dict(reading.meaning),
            "raw_hex": reading.raw.hex(" ")}


register(Recipe(
    name="max31855", title="MAX31855 thermocouple converter",
    words=("max31855", "thermocouple", "k-type"),
    bus="spi", default_mv=3300, min_mv=3000, max_mv=3600, pullups=False,
    wiring=(("SCK", "IO6"), ("SO", "IO4"), ("CS", "IO5"), ("GND", "GND"), ("VCC", "VOUT")),
    check=lambda bp, opts: {"ok": True}, action=_max31855_action, options={},
    source=DOCS + "devices/max31855/",
    notes=("the MAX31855 only sends: there is no MOSI wire",)))
