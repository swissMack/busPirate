"""The DS18B20 1-Wire thermometer recipe, and the bus search ``identify`` reuses."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ... import devices
from ...exceptions import BusPirateError
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
