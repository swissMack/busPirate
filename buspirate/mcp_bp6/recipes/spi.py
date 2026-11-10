"""SPI recipes: a flash chip (identify, optional read-only backup) and the MAX31855.

``check`` and ``action`` get only the board and the merged options. They enter
SPI mode (mode 0, up to 1 MHz) and close it again; they never touch the supply
or the pull-ups, which the engine has already set.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ... import devices
from ...devices import eeprom25
from ...mcp import jobs
from ...spiflash import SPIFlash
from .. import backup, memory
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


# -- flash: writes -------------------------------------------------------------------

SECTOR = 4096
_WRITE_WORDS = ("write", "erase", "program", "restore")


def _flash_job(opts: Options, size: Optional[int]) -> memory.WriteJob:
    if size is None:
        raise ValueError("the JEDEC ID does not give the chip's size: pass length")
    return memory.parse_job(opts, size)


def _flash_write_check(bp: Any, opts: Options) -> Dict[str, Any]:
    with open_spi(bp) as m:
        info = describe_jedec(SPIFlash(m).jedec_id())
    if info["warning"]:
        return {"ok": False, "error": "no flash chip answers (JEDEC ID %s)" % info["jedec"],
                "hint": info["warning"]}
    try:
        _flash_job(opts, info["capacity_bytes"] or _length(opts))
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "jedec": info["jedec"]}
    return {"ok": True, "jedec": info["jedec"], "identity": info["jedec"]}


def _flash_write_prepare(bp: Any, opts: Options) -> Dict[str, Any]:
    """Read the sectors the range touches, save them as a backup, and describe the change."""
    with open_spi(bp) as m:
        flash = SPIFlash(m)
        info = describe_jedec(flash.jedec_id())
        job = _flash_job(opts, info["capacity_bytes"] or _length(opts))
        start = job.offset - job.offset % SECTOR
        end = -(-(job.offset + job.length) // SECTOR) * SECTOR
        return memory.prepare(job, flash.read, chip="SPI flash %s" % info["jedec"],
                              label="spi-flash-" + info["jedec"].replace(" ", ""),
                              keep_backup=opts["backup"], span=(start, end - start))


def _flash_write_commit(bp: Any, opts: Options, prepared: Dict[str, Any]) -> Dict[str, Any]:
    """Check the chip is unchanged, erase the sectors, program the new image, read it back."""
    def write_span(start: int, image: bytes) -> None:
        flash.erase_range(start, len(image))
        flash.write(start, image)

    with open_spi(bp) as m:
        flash = SPIFlash(m)
        return memory.commit(prepared, flash.read, write_span)


register(Recipe(
    name="spi-flash-write", title="SPI flash chip: write or erase a range",
    words=("spi-flash-write",) + _WRITE_WORDS + (
        "flash", "spi", "25q", "w25q", "winbond", "bios", "firmware", "memory"),
    bus="spi", default_mv=3300, min_mv=1800, max_mv=3600, pullups=False, wiring=SPI_WIRING,
    risk="destructive", check=_flash_write_check, action=_flash_write_prepare,
    commit=_flash_write_commit, options=dict(memory.WRITE_OPTIONS),
    source=DOCS + "devices/w25q64/",
    notes=("the whole 4 KB sectors the range touches are rewritten; bytes outside the range "
           "are kept",
           "WP and HOLD must be high",
           "a chip soldered on a board may share its bus: power the board off")))


# -- SPI EEPROM and FRAM -------------------------------------------------------------

def _eeprom_part(opts: Options) -> str:
    if not opts.get("part"):
        raise ValueError("name the part with the part option; known: %s"
                         % ", ".join(sorted(eeprom25.PARTS)))
    return eeprom25.normalize(opts["part"])


def _eeprom_check(write: bool):
    def check(bp: Any, opts: Options) -> Dict[str, Any]:
        try:
            part = _eeprom_part(opts)
            if write:
                memory.parse_job(opts, eeprom25.PARTS[part][0])
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        with open_spi(bp) as m:
            value = eeprom25.status(m)
        if value == 0xFF:
            return {"ok": False, "error": "nothing answers: check CS, and that WP and HOLD "
                                          "are high"}
        return {"ok": True, "identity": part, "status": "0x%02X" % value}
    return check


def _eeprom_backup(bp: Any, opts: Options) -> Dict[str, Any]:
    """Read the whole chip and save it as a backup file; nothing is written to the chip."""
    part = _eeprom_part(opts)
    with open_spi(bp) as m:
        data = eeprom25.read(m, part, 0, eeprom25.PARTS[part][0])
    saved = backup.save(data, "spi-%s" % part)
    saved.update(part=part, first_64_hex=data[:64].hex(" "))
    return saved


def _eeprom_prepare(bp: Any, opts: Options) -> Dict[str, Any]:
    part = _eeprom_part(opts)
    job = memory.parse_job(opts, eeprom25.PARTS[part][0])
    with open_spi(bp) as m:
        return memory.prepare(job, lambda start, length: eeprom25.read(m, part, start, length),
                              chip=part, label="spi-%s" % part, keep_backup=opts["backup"])


def _eeprom_commit(bp: Any, opts: Options, prepared: Dict[str, Any]) -> Dict[str, Any]:
    """Check the chip is unchanged, write the new bytes, read them back and compare."""
    part = _eeprom_part(opts)
    with open_spi(bp) as m:
        return memory.commit(prepared, lambda start, length: eeprom25.read(m, part, start, length),
                             lambda start, image: eeprom25.write(m, part, start, image))


_EEPROM_WORDS = ("eeprom", "25lc256", "25lc", "at25", "25xx", "fram", "fm25", "mb85rs", "memory")

register(Recipe(
    name="spi-eeprom", title="25xx SPI EEPROM / FRAM: back up its contents",
    words=("spi-eeprom", "backup", "dump") + _EEPROM_WORDS,
    bus="spi", default_mv=3300, min_mv=1800, max_mv=5000, pullups=False, wiring=SPI_WIRING,
    check=_eeprom_check(False), action=_eeprom_backup, options={"part": None},
    source=DOCS + "command-reference/",
    notes=("name the part: a wrong size silently wraps and gives a wrong backup",
           "WP and HOLD must be high")))

register(Recipe(
    name="spi-eeprom-write", title="25xx SPI EEPROM / FRAM: write or erase its contents",
    words=("spi-eeprom-write",) + _WRITE_WORDS + _EEPROM_WORDS,
    bus="spi", default_mv=3300, min_mv=1800, max_mv=5000, pullups=False, wiring=SPI_WIRING,
    risk="destructive", check=_eeprom_check(True), action=_eeprom_prepare,
    commit=_eeprom_commit, options=dict({"part": None}, **memory.WRITE_OPTIONS),
    source=DOCS + "command-reference/",
    notes=("WP and HOLD must be high for the write to take",
           "name the part: a wrong size silently wraps")))


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
    words=("max31855", "thermocouple", "temperature", "k-type"),
    bus="spi", default_mv=3300, min_mv=3000, max_mv=3600, pullups=False,
    wiring=(("SCK", "IO6"), ("SO", "IO4"), ("CS", "IO5"), ("GND", "GND"), ("VCC", "VOUT")),
    check=lambda bp, opts: {"ok": True}, action=_max31855_action, options={},
    source=DOCS + "devices/max31855/",
    notes=("the MAX31855 only sends: there is no MOSI wire",)))
