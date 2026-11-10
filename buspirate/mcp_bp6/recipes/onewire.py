"""The DS18B20 1-Wire thermometer and the DS2431 / DS2433 EEPROM recipes, and the bus search ``identify`` reuses."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ... import devices
from ...devices import onewire_eeprom
from ...exceptions import BusPirateError
from .. import backup, memory
from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
FAMILY_DS18B20 = 0x28
ONEWIRE_WIRING = (("DQ", "IO0"), ("GND", "GND"), ("VDD", "VOUT"))


def search(bp: Any, read: bool = False) -> List[Dict[str, Any]]:
    """Every ROM found on the bus, named; with ``read`` each readable chip is measured too."""
    found = []
    with bp.onewire() as m:
        for rom in m.search_rom():
            entry = {"rom": rom.hex(" "), "label": devices.onewire_label(rom[0])}  # type: Dict[str, Any]
            if read:
                reading = devices.read_onewire(m, rom)
                if reading is not None:
                    entry["values"] = dict(reading.meaning)
                    match = re.match(r"\s*(-?\d+(?:\.\d+)?) °C", entry["values"].get("Temperature", ""))
                    entry["celsius"] = float(match.group(1)) if match else None
            found.append(entry)
    return found


def _check(bp: Any, opts: Dict[str, Any]) -> Dict[str, Any]:
    try:
        roms = [bytes.fromhex(e["rom"]) for e in search(bp)]
    except BusPirateError as exc:
        return {"ok": False, "error": str(exc),
                "hint": "DQ is IO0, with a pull-up (the engine switched them on); check VDD and GND"}
    if not any(rom[0] == FAMILY_DS18B20 for rom in roms):
        return {"ok": False, "error": "a device answers but it is not a DS18B20 (family 0x28)",
                "found": [r.hex(" ") for r in roms]}
    return {"ok": True}


def _action(bp: Any, opts: Dict[str, Any]) -> Dict[str, Any]:
    """Read the temperature, in degrees Celsius, from the DS18B20."""
    found = [e for e in search(bp, read=True) if e["rom"].startswith("28")]
    return {"devices": found, "count": len(found)}


register(Recipe(
    name="ds18b20", title="DS18B20 1-Wire thermometer",
    words=("ds18b20", "ds18x20", "1-wire", "onewire", "thermometer", "temperature", "dallas", "maxim"),
    bus="onewire", default_mv=3300, min_mv=3000, max_mv=5000, pullups=True,
    wiring=ONEWIRE_WIRING, check=_check, action=_action, options={},
    source=DOCS + "devices/ds18b20/",
    notes=("the Bus Pirate 6 can list only one device on the bus",)))


# -- 1-Wire EEPROM (DS2431 / DS28E07, DS2433 / DS24B33) -------------------------------

_EE_WORDS = ("ds2431", "ds28e07", "ds2433", "ds24b33", "1-wire", "onewire", "eeprom", "dallas",
             "maxim", "ibutton", "memory")
_EE_NOTES = ("one device on the bus only",
             "the protection registers are never written",
             "UNVERIFIED on hardware: a copy to memory may need a strong pull-up on DQ "
             "(add 2.2 kΩ from DQ to VDD if a write reports the copy was not confirmed)")


def _ee_family(bp: Any) -> Any:
    """(family, rom hex) of the one EEPROM on the bus, or an error dict."""
    try:
        roms = [bytes.fromhex(e["rom"]) for e in search(bp)]
    except BusPirateError as exc:
        return {"ok": False, "error": str(exc),
                "hint": "DQ is IO0, with a pull-up (the engine switched them on); check VDD and GND"}
    rom = roms[0]
    if rom[0] not in onewire_eeprom.FAMILIES:
        return {"ok": False, "error": "found family 0x%02X: that is %s, not an EEPROM" % (
            rom[0], "a thermometer" if rom[0] == FAMILY_DS18B20
            else devices.onewire_label(rom[0]) or "not a known 1-Wire EEPROM"),
            "found": rom.hex(" ")}
    return rom


def _ee_check(write: bool):
    def check(bp: Any, opts: Dict[str, Any]) -> Dict[str, Any]:
        rom = _ee_family(bp)
        if isinstance(rom, dict):
            return rom
        name, size, _ = onewire_eeprom.FAMILIES[rom[0]]
        if write:
            try:
                memory.parse_job(opts, size)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
        return {"ok": True, "identity": rom.hex(" "), "chip": name}
    return check


def _ee_rom(bp: Any) -> bytes:
    rom = _ee_family(bp)
    if isinstance(rom, dict):
        raise BusPirateError(rom["error"])
    return rom


def _ee_read(m: Any, family: int):
    return lambda start, length: onewire_eeprom.read(m, family, start, length)


def _ee_backup(bp: Any, opts: Dict[str, Any]) -> Dict[str, Any]:
    """Read the whole memory and save it as a backup file; nothing is written to the chip."""
    rom = _ee_rom(bp)
    name, size, _ = onewire_eeprom.FAMILIES[rom[0]]
    with bp.onewire() as m:
        data = onewire_eeprom.read(m, rom[0], 0, size)
    saved = backup.save(data, "onewire-%s" % rom.hex())
    saved.update(chip=name, rom=rom.hex(" "), first_64_hex=data[:64].hex(" "))
    return saved


def _ee_prepare(bp: Any, opts: Dict[str, Any]) -> Dict[str, Any]:
    rom = _ee_rom(bp)
    name, size, row = onewire_eeprom.FAMILIES[rom[0]]
    job = memory.parse_job(opts, size)
    start = job.offset - job.offset % row
    end = -(-(job.offset + job.length) // row) * row
    with bp.onewire() as m:
        return memory.prepare(job, _ee_read(m, rom[0]), chip="%s %s" % (name, rom.hex(" ")),
                              label="onewire-%s" % rom.hex(), keep_backup=opts["backup"],
                              span=(start, end - start))


def _ee_commit(bp: Any, opts: Dict[str, Any], prepared: Dict[str, Any]) -> Dict[str, Any]:
    """Check the chip is unchanged, write the new rows, read them back and compare."""
    rom = _ee_rom(bp)
    with bp.onewire() as m:
        return memory.commit(prepared, _ee_read(m, rom[0]),
                             lambda start, image: onewire_eeprom.write(m, rom[0], start, image))


register(Recipe(
    name="onewire-eeprom", title="DS2431 / DS2433 1-Wire EEPROM: back up its contents",
    words=("onewire-eeprom", "backup", "dump") + _EE_WORDS,
    bus="onewire", default_mv=3300, min_mv=3000, max_mv=5000, pullups=True,
    wiring=ONEWIRE_WIRING, check=_ee_check(False), action=_ee_backup, options={},
    source=DOCS + "devices/ds18b20/", notes=_EE_NOTES))

register(Recipe(
    name="onewire-eeprom-write", title="DS2431 / DS2433 1-Wire EEPROM: write or erase its contents",
    words=("onewire-eeprom-write", "write", "erase", "program", "restore") + _EE_WORDS,
    bus="onewire", default_mv=3300, min_mv=3000, max_mv=5000, pullups=True,
    wiring=ONEWIRE_WIRING, risk="destructive", check=_ee_check(True), action=_ee_prepare,
    commit=_ee_commit, options=dict(memory.WRITE_OPTIONS),
    source=DOCS + "devices/ds18b20/", notes=_EE_NOTES))
