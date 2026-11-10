"""DDR4 and DDR5 SPD recipes: read the module's ID EEPROM from a DIMM plank. Read only.

The plank makes its own 3.3 V and has its own pull-ups, so the recipes ask the
Bus Pirate for 5 V on the plank's input and leave the pull-ups off. Nothing is
ever written to the module.
"""

from __future__ import annotations

from typing import Any, Dict

from ...devices import spd
from ...mcp import jobs
from .. import backup
from . import Recipe, register
from .i2c import DOCS, _hex, _make_check, _open

Options = Dict[str, Any]

DDR_WIRING = (("5V", "VOUT"), ("GND", "GND"), ("SDA", "IO0"), ("SCL", "IO1"))
SPD_ADDRESSES = tuple(range(0x50, 0x58))


def _make_ddr_check(kind: str, type_byte: int, pointer: bytes):
    base = _make_check("%s module" % kind, (), SPD_ADDRESSES, 400)

    def check(bp: Any, opts: Options) -> Dict[str, Any]:
        out = base(bp, opts)
        if not out.get("ok"):
            return out
        address = jobs.check_address(opts["address"])
        with _open(bp, 400) as m:
            found = m.read_after_write(address, pointer, 1)[0]
        if found != type_byte:
            return {"ok": False, "error": "the SPD at %s says memory type 0x%02X, not %s "
                    "(0x%02X): is this a %s module, seated fully in the %s plank?"
                    % (_hex(address), found, kind, type_byte, kind, kind)}
        return {"ok": True, "address": _hex(address)}
    return check


def _make_ddr_action(kind: str, reader):
    def action(bp: Any, opts: Options) -> Dict[str, Any]:
        """Read the whole SPD, decode it and save the raw image; nothing is written."""
        address = opts["address"]
        with _open(bp, 400) as m:
            data = reader(m, address)
        out = spd.decode(data)
        part = out.get("part_number") or "unknown"
        out.update(backup.save(data, "%s-spd-%s" % (kind.lower(), part)))
        out["address"] = _hex(address)
        return out
    return action


def _ddr(kind: str, type_byte: int, pointer: bytes, reader, notes) -> None:
    register(Recipe(
        name="%s-spd" % kind.lower(), title="%s module: read and decode its SPD" % kind,
        words=("%s-spd" % kind.lower(), kind.lower(), "spd", "dimm", "ram", "memory", "module",
               "serial presence detect"),
        bus="i2c", default_mv=5000, min_mv=4500, max_mv=5000, pullups=False, wiring=DDR_WIRING,
        check=_make_ddr_check(kind, type_byte, pointer),
        action=_make_ddr_action(kind, reader), options={"address": 0x50},
        source=DOCS + "devices/", notes=notes))


_COMMON = ("take the module out of the computer; seat it in the plank before power-on",
           "read only: writing SPD can stop a module from booting")

_ddr("DDR4", 0x0C, b"\x02", spd.read_ddr4, _COMMON)
_ddr("DDR5", 0x12, b"\x82", spd.read_ddr5,
     _COMMON + ("the plank's HSA jumper goes to GND (offline mode, address 0x50)",))
