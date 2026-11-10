"""The IO pins: drive some, and read every pin's level and voltage."""

from __future__ import annotations

from typing import Any, Dict

from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
PINS = tuple("IO%d" % n for n in range(8))
Options = Dict[str, Any]


def _masks(setting: Any) -> Dict[str, int]:
    """``{"IO2": 1}`` into the four BPIO2 masks; a value of None releases the pin to an input."""
    if not isinstance(setting, dict):
        raise ValueError('set must be a mapping such as {"IO2": 1}, not %r' % (setting,))
    direction_mask = direction = value_mask = value = 0
    for name, level in setting.items():
        if name not in PINS:
            raise ValueError("%r is not a pin: use IO0 to IO7" % (name,))
        bit = 1 << PINS.index(name)
        direction_mask |= bit
        if level is None:
            continue
        if isinstance(level, bool) or level not in (0, 1):
            raise ValueError("%s: use 1 (high), 0 (low) or None (input), not %r" % (name, level))
        direction |= bit
        value_mask |= bit
        if level:
            value |= bit
    return {"direction_mask": direction_mask, "direction": direction,
            "value_mask": value_mask, "value": value}


def _check(bp: Any, opts: Options) -> Dict[str, Any]:
    try:
        if opts["set"]:
            _masks(opts["set"])
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def _action(bp: Any, opts: Options) -> Dict[str, Any]:
    """Drive the pins named in set, then read every pin's direction, level and voltage."""
    out = {"set": dict(opts["set"] or {})}  # type: Dict[str, Any]
    if opts["set"]:
        bp.set_pins(**_masks(opts["set"]))
    if opts["read"] or opts["set"]:
        pins = bp.read_pins()
        out["directions"] = {n: "out" if pins["direction"] >> i & 1 else "in"
                             for i, n in enumerate(PINS)}
        out["levels"] = {n: pins["value"] >> i & 1 for i, n in enumerate(PINS)}
        out["mv"] = dict(pins["mv"])
    return out


register(Recipe(
    name="pins", title="IO pins: drive them and read their levels and voltages",
    words=("pins", "gpio", "io", "pin", "voltage", "level", "adc", "drive"),
    bus="pins", default_mv=0, min_mv=1200, max_mv=5000, pullups=False,
    wiring=(("GND", "GND"), ("VCC", "VOUT")), check=_check, action=_action,
    options={"set": None, "read": True}, source=DOCS + "command-reference/",
    notes=("the pins follow VOUT: tell the owner's target voltage as millivolts, or feed the "
           "target's own supply into VOUT",)))
