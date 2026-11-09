"""Wiring steps with each board's own cable colours.

Every step carries both the pin label and the wire colour, so an AI client can
tell a person "connect IO0 (orange) to SDA" and never leave them guessing.
"""

from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .. import boards
from ..boards.bitpirate import DOCK_HEADER
from ..boards.bp6 import BP6_CABLE, BP6_HEADER
from ..web.wiring import colour_name

JOBS = ("i2c", "spi", "uart", "onewire", "rawwire", "pins")


@dataclass(frozen=True)
class WiringStep:
    pin: str
    colour: str
    target: str
    note: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def cable_colour(variant: str, pin: str) -> str:
    """The wire colour for ``pin`` on ``variant``; '' if the board has none."""
    if variant == "bitpirate":
        # VIO and GND are named, not positional: the dock header runs GND..VIO
        # where the Bus Pirate 6 runs VOUT..GND.
        if pin == "VIO":
            return BP6_CABLE["VOUT"]
        if pin == "GND":
            return BP6_CABLE["GND"]
        if pin in DOCK_HEADER:
            return BP6_CABLE[BP6_HEADER[DOCK_HEADER.index(pin)]]
        return ""
    if variant == "bp6":
        return BP6_CABLE.get(pin, "")
    return colour_name(pin)


def _rows(variant: str, job: str) -> List[Dict[str, Any]]:
    board = boards.get(variant)
    override = board.wiring.get("panels", {}).get(job, {})
    if "wiring" in override:
        return list(override["wiring"])
    if board.wiring.get("cable", True) is False:
        raise KeyError("%s has no wiring for %r" % (variant, job))
    try:
        panel = importlib.import_module("buspirate.web.panels." + job).PANEL
    except ImportError:
        raise KeyError("no wiring for %r" % job)
    return [w.to_json() for w in panel.wiring]


def wiring_steps(variant: str, job: str) -> List[WiringStep]:
    """The wires to connect for ``job`` on ``variant``. KeyError if none."""
    steps = []
    for row in _rows(variant, job):
        pin = row["signal"]
        colour = row.get("colour") or ""
        if variant in ("bp6", "bitpirate") or not colour:
            colour = cable_colour(variant, pin)
        elif variant in ("v3", "v4"):
            colour = colour_name(pin) or colour
        steps.append(WiringStep(pin, colour or pin, row.get("target", ""), row.get("note", "")))
    return steps
