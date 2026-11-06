"""Helpers the board definitions share for their wiring and LED data."""

from __future__ import annotations

from typing import Dict


def wire(signal: str, target: str, note: str = "") -> Dict[str, str]:
    """One row of a panel's wiring table, for a board with no probe-cable colours."""
    return {"signal": signal, "colour": "", "target": target, "note": note}


#: The start of every Bus Pirate v3/v4 LED note.
LED_NOTE_COMMON = (
    "There is no command that reads the LEDs back, so these are inferred from "
    "what the dashboard believes it has asked the board to do, not measured. "
    "The firmware can change them on its own — an overrun turns MODE off — so "
    "trust the board over this picture."
)
