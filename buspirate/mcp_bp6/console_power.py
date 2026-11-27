"""Mode, supply and pull-ups through the Bus Pirate 6's text terminal.

Each helper takes an open ``Console`` (``with bp.console() as con``) and
raises ``TerminalError`` when the firmware did not do what was asked. The
strings parsed here are the firmware's own (research doc section 7).
"""

from __future__ import annotations

import re
from typing import Any, Dict

from ..bp6.console import Reply, TerminalError

MIN_MV, MAX_MV = 800, 5000
MAX_MA = 500
ENABLED = "Power supply:  Enabled"
_READINGS = re.compile(
    r"Vreg output: (\d+)\.(\d+)V, Vref/Vout pin: (\d+)\.(\d+)V, Current: (\d+)\.(\d+)mA")


def set_mode(con: Any, name: str, flags: str = "") -> Reply:
    """``m <name> [flags]``; raises unless the prompt then names that mode."""
    line = "m %s" % name + (" %s" % flags if flags else "")
    reply = con.command(line)
    if reply.error:
        raise TerminalError("%s failed: %s" % (line, reply.error))
    # The prompt spells HiZ in mixed case; every other mode is upper case.
    if reply.mode.upper() != name.upper():
        raise TerminalError("%s left the board in %s mode, not %s"
                            % (line, reply.mode or "an unknown", name.upper()))
    return reply


def _milli(whole: str, frac: str) -> int:
    return int(round((int(whole) + int(frac) / 10.0 ** len(frac)) * 1000))


def power_on(con: Any, mv: int, ma: int) -> Dict[str, Any]:
    """``W <volts> <mA>`` with a planned voltage and limit; the board's readings."""
    if isinstance(mv, bool) or not isinstance(mv, int) or not MIN_MV <= mv <= MAX_MV:
        raise TerminalError("the supply takes %d-%d mV, not %r; nothing was switched on"
                            % (MIN_MV, MAX_MV, mv))
    if isinstance(ma, bool) or not isinstance(ma, int) or not 0 <= ma <= MAX_MA:
        raise TerminalError("the current limit is 0-%d mA, not %r; nothing was switched on"
                            % (MAX_MA, ma))
    reply = con.command("W %.2f %d" % (mv / 1000.0, ma))
    if reply.error:
        raise TerminalError(reply.error)
    if ENABLED not in reply.text:
        raise TerminalError("the supply did not report itself enabled: %s"
                            % reply.text.strip()[-200:])
    match = _READINGS.search(reply.text)
    if match is None:
        raise TerminalError("the supply gave no readings: %s" % reply.text.strip()[-200:])
    g = match.groups()
    return {"vreg_mv": _milli(g[0], g[1]), "vout_mv": _milli(g[2], g[3]),
            "current_ma": int(g[4]) + int(g[5]) / 10.0 ** len(g[5])}


def pullups(con: Any, on: bool) -> Reply:
    """``P`` or ``p``. A low-voltage warning is text, not an error."""
    reply = con.command("P" if on else "p")
    if reply.error:
        raise TerminalError(reply.error)
    return reply
