"""Smart card (SIM or bank card): read its answer to reset. Read-only."""

from __future__ import annotations

from typing import Any, Dict

from ...bp6 import smartcard
from . import Recipe, register

Options = Dict[str, Any]

#: The baud ``terminal_flags`` fixes; ISO 7816 sets baud = clock / 372.
BAUD = smartcard.BAUD
MAX_WAIT_S = 10


def _check(con: Any, opts: Options) -> Dict[str, Any]:
    hz = opts.get("clock_hz")
    if isinstance(hz, bool) or not isinstance(hz, int) or not 1_000_000 <= hz <= 5_000_000:
        return {"ok": False, "error": "clock_hz must be a whole number of Hz from 1000000 to "
                "5000000 (1-5 MHz), not %r" % (hz,)}
    baud = round(hz / 372)
    if abs(baud - BAUD) > BAUD * 0.02:
        return {"ok": False, "error": "clock_hz %d gives %d baud (clock / 372) but the terminal "
                "listens at %d: use about %d Hz" % (hz, baud, BAUD, BAUD * 372)}
    wait = opts.get("wait_s")
    if isinstance(wait, bool) or not isinstance(wait, (int, float)) or not 0 < wait <= MAX_WAIT_S:
        return {"ok": False, "error": "wait_s must be a number of seconds above 0 and at most "
                "%d, not %r" % (MAX_WAIT_S, wait)}
    return {"ok": True}


def _read(con: Any, opts: Options) -> Dict[str, Any]:
    # read_atr starts the IO1 clock and stops it itself, so no PWM is left running.
    return smartcard.read_atr(con, opts["clock_hz"], float(opts["wait_s"]))


register(Recipe(
    name="smartcard-atr", title="Smart card (SIM or bank card): read its answer to reset",
    words=("sim", "smartcard", "smart", "card", "atr", "iso7816", "bank", "chip card"),
    bus="uart", transport="terminal", terminal_mode="hduart",
    terminal_flags="-b 9600 -d 8 -p even -s 2 -l listen",
    default_mv=3000, min_mv=1800, max_mv=5000, milliamps=100, pullups=True,
    target_powered_ok=False, options={"clock_hz": 3_571_200, "wait_s": 1.0},
    check=_check, action=_read,
    wiring=(("C7 I/O", "IO0"), ("C3 CLK", "IO1"), ("C2 RST", "IO2"), ("C1 VCC", "VOUT"),
            ("C5 GND", "GND")),
    notes=("cards are 5 V (class A), 3 V (B) or 1.8 V (C): use the card's class; "
           "3 V suits most SIMs",
           "read-only: this never sends a command or a PIN to the card"),
    source="https://docs.buspirate.com/docs/devices/sim-bank-ic-cards/"))
