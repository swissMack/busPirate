"""Wiring steps with each board's own cable colours.

Every step carries both the pin label and the wire colour, so an AI client can
tell a person "connect IO0 (orange) to SDA" and never leave them guessing.
"""

from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

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


# Notes the dashboard words for its own panels, reworded for the MCP tools.
_NOTE_OVERRIDES = {
    ("bp6", "VOUT"): "the adjustable supply — power_plan sets it, and it stays off until you confirm",
}


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
        note = _NOTE_OVERRIDES.get((variant, pin), row.get("note", ""))
        steps.append(WiringStep(pin, colour or pin, row.get("target", ""), note))
    return steps


_V3_V4 = ("v3", "v4")

#: The dashboard's notes under each job's panel, reworded for an AI client.
#: Each rule: (text the note contains, boards it is true for or None for all,
#: replacement). A note matched on a board outside its list is dropped, so the
#: v3 cable warning never reaches a Bus Pirate 6. Unmatched notes pass through.
_NOTE_REWRITES: Tuple[Tuple[str, Optional[Tuple[str, ...]], str], ...] = (
    ("Seeed/Adafruit", _V3_V4,
     "Colours and pin order are the Seeed/Adafruit cable, the firmware reference: pin 1 is "
     "MISO (black) and pin 10 is GND (brown). SparkFun cables are usually reversed and the "
     "v2go differs, so check these colours against your own cable."),
    ("selecting this panel", _V3_V4,
     "The pin tools work in bitbang mode, so using them leaves whatever protocol mode the "
     "board was in."),
    ("Power & pull-ups", None,
     "I2C needs pull-ups: power_plan switches them on (10 kΩ) unless pullups is false."),
    ("The dashboard finds one device", None,
     "onewire_scan finds one device. With several on the bus, use the board's own "
     "terminal: 'm 1wire', then 'scan'."),
    ("The dashboard sets these pins", None,
     "The driver sets these pins itself each time it enters a mode: the Bus Pirate 6 "
     "layout of the dock's header, not the firmware's own defaults. Bus Pirate 5/6 "
     "adapters plug straight in."),
)


def _dashboard_notes(variant: str, job: str) -> List[str]:
    board = boards.get(variant)
    override = board.wiring.get("panels", {}).get(job, {}) if board is not None else {}
    if "notes" in override:
        return list(override["notes"])
    try:
        panel = importlib.import_module("buspirate.web.panels." + job).PANEL
    except ImportError:
        return []
    return list(panel.notes)


def job_notes(variant: str, job: str) -> List[str]:
    """The notes for ``job`` on ``variant``, worded for the MCP tools."""
    notes = []
    for note in _dashboard_notes(variant, job):
        for needle, only, replacement in _NOTE_REWRITES:
            if needle in note:
                note = replacement if only is None or variant in only else None
                break
        if note is not None:
            notes.append(note)
    return notes
