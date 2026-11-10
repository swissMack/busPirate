"""I2C recipes: the character LCD, the catalogue's sensors, serial memories and a bus scan.

``check`` and ``action`` get only the board and the merged options. They enter
I2C mode, set the speed and close it again; they never touch the supply or the
pull-ups, which the engine has already set. A failed check scans the bus and
says what *is* there, so the owner can see a wrong address at a glance.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ... import devices
from ...devices import eeprom24, hd44780
from ...mcp import jobs
from .. import backup
from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
I2C_WIRING = (("VCC", "VOUT"), ("GND", "GND"), ("SDA", "IO0"), ("SCL", "IO1"))
EEPROM_ADDRESSES = tuple(range(0x50, 0x58))  # 0x50 + A0-A2
NO_DEVICE_HINT = ("nothing answers on the bus: check the wiring (SDA on IO0, SCL on IO1), "
                  "the supply and the pull-ups, then re-run with token=None")

Options = Dict[str, Any]


# -- the bus ------------------------------------------------------------------------

def _open(bp: Any, khz: int):
    """Enter I2C mode at the fastest speed not above ``khz``. Close it when done."""
    m = bp.i2c()
    try:
        m.set_speed(jobs._pick(bp.profile.i2c_speeds, khz * 1000))
    except BaseException:
        m.close()
        raise
    return m


def _hex(address: int) -> str:
    return "0x%02X" % address


def _found(m: Any) -> List[Dict[str, str]]:
    return [{"address": _hex(a), "label": devices.i2c_label(a)} for a in m.scan()]


def _catalogue(names: Tuple[str, ...]) -> List[devices.Device]:
    return [d for d in devices.devices("i2c") if d.name in names]


def _identify(m: Any, names: Tuple[str, ...], address: int) -> Optional[devices.Device]:
    """The named chip at ``address`` whose probe accepts it."""
    for device in _catalogue(names):
        if address in device.addresses and (device.probe is None or device.probe(m, address)):
            return device
    return None


def _hint(address: int, found: List[Dict[str, str]], family: Iterable[int], title: str) -> str:
    if not found:
        return NO_DEVICE_HINT
    others = [f for f in found if int(f["address"], 16) != address
              and int(f["address"], 16) in family]
    if others:
        other = others[0]
        return ("%s answers at %s: re-run with address %s (plan it again: a plan fixes the "
                "address)" % (other["label"] or title, other["address"], other["address"]))
    return ("no %s at %s; the bus has %s. If one of those is your device, plan its own recipe"
            % (title, _hex(address),
               ", ".join((f["address"] + " " + f["label"]).strip() for f in found)))


def _make_check(title: str, names: Tuple[str, ...], family: Iterable[int], khz: int,
                validate: Optional[Callable[[Options], None]] = None
                ) -> Callable[[Any, Options], Dict[str, Any]]:
    """The check: the address answers, and (for a catalogue chip) its probe accepts it."""
    family = tuple(family)

    def check(bp: Any, opts: Options) -> Dict[str, Any]:
        try:
            address = jobs.check_address(opts["address"])
            if validate:
                validate(opts)
        except (ValueError, TypeError) as exc:
            return {"ok": False, "error": str(exc)}
        with _open(bp, khz) as m:
            if address not in m.scan([address]):
                error = "nothing answers at %s" % _hex(address)
            elif not names or _identify(m, names, address):
                return {"ok": True, "address": _hex(address)}
            else:
                error = "something answers at %s but it is not a %s" % (_hex(address), title)
            found = _found(m)
        return {"ok": False, "error": error, "found": found,
                "hint": _hint(address, found, family, title)}
    return check


# -- the character LCD --------------------------------------------------------------

def _validate_lcd(opts: Options) -> None:
    if opts["size"] not in hd44780.SIZES:
        raise ValueError("size must be one of %s, not %r"
                         % (", ".join(hd44780.SIZES), opts["size"]))


def _lcd_action(bp: Any, opts: Options) -> Dict[str, Any]:
    """Show the message on the character display; you check it by eye."""
    address = opts["address"]
    transfers = [data for data, _ in
                 hd44780.compose(opts["message"], opts["size"], bool(opts["backlight"])) if data]
    with _open(bp, 100) as m:
        sent = hd44780.send(m, address, transfers)
    return {"address": _hex(address), "size": opts["size"], "sent_bytes": sent,
            "steps": len(transfers), "check": jobs.LCD_CHECK}


# -- catalogue sensors --------------------------------------------------------------

def _measure_action(names: Tuple[str, ...], khz: int, what: str):
    def action(bp: Any, opts: Options) -> Dict[str, Any]:
        address = opts["address"]
        with _open(bp, khz) as m:
            device = _identify(m, names, address)
            if device is None:  # the check passed a moment ago; the chip went away
                return {"error": "no %s answers at %s any more" % (names[0], _hex(address))}
            reading = device.measure(m, address)
        return {"device": reading.device, "address": reading.where,
                "values": dict(reading.meaning), "raw_hex": reading.raw.hex(" ")}
    action.__doc__ = "Read %s from the sensor." % what
    return action


def _sensor(name: str, title: str, words: Tuple[str, ...], names: Tuple[str, ...],
            address: int, khz: int, what: str, source: str, default_mv: int = 3300,
            min_mv: int = 1800, max_mv: int = 5000, notes: Tuple[str, ...] = ()) -> Recipe:
    family = {a for d in _catalogue(names) for a in d.addresses}
    return register(Recipe(
        name=name, title=title, words=words, bus="i2c", default_mv=default_mv, min_mv=min_mv,
        max_mv=max_mv, pullups=True, wiring=I2C_WIRING,
        check=_make_check(names[0] if len(names) == 1 else "/".join(names), names, family, khz),
        action=_measure_action(names, khz, what), options={"address": address},
        source=source, notes=notes))


_TEMP = ("temperature", "thermometer", "sensor")

_sensor("aht20", "AHT20 temperature and humidity sensor",
        ("aht20", "aht10", "humidity") + _TEMP, ("AHT20",), 0x38, 100,
        "temperature and humidity", DOCS + "command-reference/")
_sensor("bmp280", "BMP280 / BME280 pressure and temperature sensor",
        ("bmp280", "bme280", "bmp", "pressure", "barometer") + _TEMP, ("BMP280", "BME280"),
        0x76, 100, "pressure and temperature (and humidity on a BME280)",
        DOCS + "command-reference/",
        notes=("a bare BMP280/BME280 chip is a 3.6 V part; breakouts with a regulator take 5 V",))
_sensor("sht3x", "SHT30 / SHT31 / SHT35 temperature and humidity sensor",
        ("sht3x", "sht30", "sht31", "sht35", "humidity") + _TEMP, ("SHT3x",), 0x44, 400,
        "temperature and humidity", DOCS + "devices/sht30-sht31-sht35/",
        min_mv=2150)
_sensor("sht4x", "SHT40 / SHT41 / SHT43 / SHT45 temperature and humidity sensor",
        ("sht4x", "sht40", "sht41", "sht43", "sht45", "humidity") + _TEMP, ("SHT4x",), 0x44, 400,
        "temperature and humidity", DOCS + "devices/sht40-sht41-sht43-sht45/",
        max_mv=3600, notes=("the SHT4x is not 5 V tolerant: 3.6 V is its limit",))
_sensor("si7021", "Si7021 / HTU21 / SHT21 temperature and humidity sensor",
        ("si7021", "htu21", "sht21", "humidity") + _TEMP, ("Si7021",), 0x40, 400,
        "temperature and humidity", DOCS + "devices/si7021/", min_mv=1900, max_mv=3600,
        notes=("the Si7021 takes 3.6 V at most",))
_sensor("tsl2561", "TSL2561 light sensor",
        ("tsl2561", "lux", "light", "luminosity"), ("TSL2561",), 0x39, 400,
        "the light level in lux", DOCS + "devices/tsl2561/", min_mv=2700, max_mv=3600,
        notes=("the TSL2561 takes 3.6 V at most",))
_sensor("tcs3472x", "TCS3472x colour sensor (TCS34725)",
        ("tcs3472x", "tcs34725", "colour", "color", "rgb"), ("TCS3472x",), 0x29, 400,
        "the red, green, blue and clear levels", DOCS + "devices/tcs3472x/",
        min_mv=2700, max_mv=3300, notes=("the chip itself takes 3.3 V at most",))
_sensor("ms5611", "MS5611 pressure and temperature sensor",
        ("ms5611", "pressure", "barometer", "altimeter") + _TEMP, ("MS5611",), 0x76, 100,
        "pressure and temperature", DOCS + "command-reference/", max_mv=3600,
        notes=("the MS5611 takes 3.6 V at most",))


# -- serial memories ----------------------------------------------------------------

def _validate_part(opts: Options) -> None:
    if str(opts["part"]).upper() not in eeprom24.SIZES:
        raise ValueError("unknown part %r; known: %s"
                         % (opts["part"], ", ".join(sorted(eeprom24.SIZES))))


def _backup_action(khz: int):
    def action(bp: Any, opts: Options) -> Dict[str, Any]:
        """Read the whole chip and save it as a backup file; nothing is written to the chip."""
        address, part = opts["address"], str(opts["part"]).upper()
        with _open(bp, khz) as m:
            data = eeprom24.read(m, address, part, chunk=bp.status().max_read or 256)
        saved = backup.save(data, "i2c-%s-%s" % (part, _hex(address)))
        saved.update(part=part, address=_hex(address), first_64_hex=data[:64].hex(" "))
        return saved
    return action


register(Recipe(
    name="i2c-eeprom", title="24xx I2C EEPROM: back up its contents",
    words=("i2c-eeprom", "eeprom", "24c02", "24c04", "24c08", "24c16", "24c32", "24c64",
           "24c256", "at24c256", "24lc", "24xx", "memory", "backup", "dump"),
    bus="i2c", default_mv=3300, min_mv=1800, max_mv=5000, pullups=True, wiring=I2C_WIRING,
    check=_make_check("I2C EEPROM", (), EEPROM_ADDRESSES, 100, _validate_part),
    action=_backup_action(100), options={"address": 0x50, "part": "24C02"},
    source=DOCS + "devices/at24c256/",
    notes=("name the part: a wrong size silently wraps and gives a wrong backup",
           "keep the chip's WP pin low")))

register(Recipe(
    name="fram", title="MB85RC256V I2C FRAM: back up its contents",
    words=("fram", "mb85rc256v", "mb85rc", "ferroelectric", "memory", "backup", "dump"),
    bus="i2c", default_mv=3300, min_mv=2700, max_mv=5000, pullups=True, wiring=I2C_WIRING,
    check=_make_check("MB85RC256V FRAM", (), EEPROM_ADDRESSES, 400, _validate_part),
    action=_backup_action(400), options={"address": 0x50, "part": "MB85RC256V"},
    source=DOCS + "devices/mb85rc256v/"))


# -- the character LCD and the scan, registered last so the sensors rank first ------

register(Recipe(
    name="lcd", title="HD44780 character LCD with a PCF8574 I2C backpack",
    words=("lcd", "display", "1602", "2004", "hd44780", "character display", "pcf8574",
           "backpack"),
    bus="i2c", default_mv=5000, min_mv=3000, max_mv=5000, pullups=True, wiring=I2C_WIRING,
    check=_make_check("LCD backpack", ("LCD (PCF8574 backpack)",), (0x27, 0x3F), 100,
                      _validate_lcd),
    action=_lcd_action,
    options={"address": 0x27, "message": "Bus Pirate 6", "size": "16x2", "backlight": True},
    source="https://github.com/swissMack/busPirate (buspirate/devices/hd44780.py; "
           "not on docs.buspirate.com)",
    notes=("the backpack is usually at 0x27; some are at 0x3F: pass address 0x3F",)))


def _scan_action(bp: Any, opts: Options) -> Dict[str, Any]:
    """Scan the bus and name every device that answers."""
    with _open(bp, 100) as m:
        found = _found(m)
    return {"devices": found, "count": len(found)}


register(Recipe(
    name="i2c-scan", title="Scan the I2C bus and name what answers",
    words=("i2c-scan", "scan", "i2c", "find devices", "addresses", "what is connected"),
    bus="i2c", default_mv=3300, min_mv=1800, max_mv=5000, pullups=True, wiring=I2C_WIRING,
    check=lambda bp, opts: {"ok": True}, action=_scan_action, options={},
    source=DOCS + "command-reference/"))
