"""DDR4 and DDR5 SPD recipes: read the module's ID EEPROM from a DIMM plank. Read only.

The plank makes its own 3.3 V and has its own pull-ups, so the recipes ask the
Bus Pirate for 5 V on the plank's input and leave the pull-ups off. Nothing is
ever written to the module.
"""

from __future__ import annotations

from typing import Any, Dict

from ...devices import spd
from ...exceptions import NackError
from ...mcp import jobs
from .. import backup
from . import Recipe, register
from .i2c import DOCS, _hex, _open

Options = Dict[str, Any]

DDR_WIRING = (("5V", "VOUT"), ("GND", "GND"), ("SDA", "IO0"), ("SCL", "IO1"))
SPD_ADDRESSES = tuple(range(0x50, 0x58))


def _make_ddr_check(kind: str, type_byte: int, pointer: bytes):
    """The address answers and byte 2 names the right memory type.

    Only 0x50-0x57 are ever addressed here: 0x30-0x35 are the EE1004 write-protection
    commands, so unlike the generic I2C check this one never scans the whole bus.
    """
    question = "is this a %s module, seated fully in the %s plank?" % (kind, kind)

    def check(bp: Any, opts: Options) -> Dict[str, Any]:
        try:
            address = jobs.check_address(opts["address"])
            if address not in SPD_ADDRESSES:
                raise ValueError("an SPD answers at 0x50-0x57, not %s" % _hex(address))
        except (ValueError, TypeError) as exc:
            return {"ok": False, "error": str(exc)}
        with _open(bp, 400) as m:
            if address not in m.scan([address]):
                found = [{"address": _hex(a), "label": ""} for a in m.scan(SPD_ADDRESSES)]
                hint = ("nothing answers at %s; SPD addresses that answer: %s"
                        % (_hex(address), ", ".join(f["address"] for f in found) or "none")
                        if found else "nothing answers on 0x50-0x57: check the wiring and "
                        "that the module is seated, then re-run with token=None")
                return {"ok": False, "error": "nothing answers at %s: %s" % (_hex(address), question),
                        "found": found, "hint": hint}
            try:
                if kind == "DDR4":
                    # The page survives between runs while the plank stays powered.
                    spd._select_page(m, 0)
                else:
                    m.write(address, bytes([0x0B, 0]))  # MR11: page 0
                found_type = m.read_after_write(address, pointer, 1)[0]
            except (NackError, spd.SpdError):
                found_type = -1
        if found_type != type_byte:
            seen = "no memory type" if found_type < 0 else "memory type 0x%02X" % found_type
            return {"ok": False, "error": "the SPD at %s says %s, not %s (0x%02X): %s"
                    % (_hex(address), seen, kind, type_byte, question)}
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
