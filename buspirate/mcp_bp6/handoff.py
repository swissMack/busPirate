"""Lend the Bus Pirate 6 to flashrom, avrdude or PulseView, and take it back.

A hand-off closes the BPIO2 port (nothing is sent on it) and switches the
board's second port to a binary mode the other program speaks: Legacy for
flashrom and avrdude, SUMP for PulseView (research doc section 8). While the
board is lent, ``state.of(session).lent`` names the program, and the server
refuses every board tool but connect, hiz and board_status.

Taking it back:

* Legacy locks the terminal. ``q``, then ``y``, resets the board: its ports
  vanish and come back, and the supply is off. The session is dropped, and
  the caller connects again.
* SUMP leaves the terminal free: ``binmode 2`` (not saved) selects BPIO2
  again, the BPIO2 port is reopened, and the board goes to HiZ.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict

from ..bp6.console import Answer, TerminalError
from ..exceptions import BusPirateError
from ..mcp.session import BoardGone, NotConnected
from . import state

LEGACY, SUMP = "legacy", "sump"
#: Each program's binary mode.
KINDS = {"flashrom": LEGACY, "avrdude": LEGACY, "pulseview": SUMP}
#: The binmode menu numbers used, and a word their menu entry must hold.
MENU = {1: "SUMP", 2: "BPIO2", 5: "Legacy"}
HOW = {
    LEGACY: "quit %s first; the Bus Pirate then resets, its ports vanish for a few "
            "seconds, and the supply goes off",
    SUMP: "close %s first; the logic analyzer is switched off, BPIO2 comes back and the "
          "supply goes off",
}
SAVE = "Save setting?"
EXIT_LEGACY = "Exit legacy binary mode"
RESETTING = "Resetting Bus Pirate"
#: How long a reset may take to drop the ports, and then to bring them back.
GONE_WAIT_S = 3.0
BACK_WAIT_S = 10.0
_ENTRY = re.compile(r"^\s*(\d+)\. (.+?)\s*$", re.M)


def how_to_return(to: str) -> str:
    return "call connect (or hiz) to take it back — " + HOW[KINDS[to]] % to


def lent_error(lent: Dict[str, Any]) -> str:
    """What every refused tool says while the board is lent."""
    return "the board is lent to %s; %s" % (lent["to"], how_to_return(lent["to"]))


def check_menu(con: Any, number: int) -> None:
    """Raise unless the printed ``binmode`` menu has the expected entry at ``number``."""
    reply = con.command("binmode", answers=[Answer("x to exit", "x", wait_s=0.05)])
    menu = {int(n): name for n, name in _ENTRY.findall(reply.text)}
    if MENU[number] not in menu.get(number, ""):
        listed = "; ".join("%d. %s" % kv for kv in sorted(menu.items())) or reply.text[-200:]
        raise TerminalError("the binmode menu does not have %s at %d, so nothing was "
                            "switched; it lists: %s" % (MENU[number], number, listed))


def lend(session: Any, bp: Any, to: str) -> Dict[str, Any]:
    """Mark the board lent to ``to`` and close its BPIO2 port. Sends nothing.

    Called before the binary mode is switched, so a switch that fails still
    leaves the board marked lent, and connect or hiz resets it.
    """
    kind = KINDS[to]
    st = state.of(session)
    st.lent = {"to": to, "kind": kind, "port": bp.port, "how": HOW[kind] % to}
    st.terminal_mode = None
    st.pwm_pins.clear()
    session.last_recipe = None
    bp.release_binary()
    return {"lent_to": to, "binary_port": bp.port, "how_to_return": how_to_return(to)}


def _wait_for_reset(session: Any) -> None:
    """Wait for the ports to vanish (the reset), then to come back."""
    deadline = time.monotonic() + GONE_WAIT_S
    while time.monotonic() < deadline and session.candidates():
        time.sleep(0.05)
    deadline = time.monotonic() + BACK_WAIT_S
    while time.monotonic() < deadline and not session.candidates():
        time.sleep(0.1)


def _reclaim_legacy(session: Any, bp: Any) -> bool:
    """``q`` then ``y`` on the locked terminal. True if the board reset."""
    with bp.raw_console() as con:
        reply = con.command("q", timeout=5.0, until=RESETTING,
                            answers=[Answer(EXIT_LEGACY, "y")])
    return RESETTING in reply.text


def _reclaim_sump(session: Any, bp: Any) -> None:
    with bp.console() as con:
        check_menu(con, 2)
        reply = con.command("binmode 2", answers=[Answer(SAVE, "n", wait_s=0.05)])
        if reply.error:
            raise TerminalError("binmode 2 failed: %s" % reply.error)
    bp.reattach_binary(bp.bpio2_settle)
    bp.hiz()


def reclaim(session: Any) -> Dict[str, Any]:
    """Take a lent board back. ``lent`` is None afterwards, whatever happened.

    ``reconnect`` True means the session was dropped (the board reset, or
    could not be reached) and the caller should connect again.
    """
    st = state.of(session)
    lent = st.lent
    if lent is None:
        return {"reclaimed": None, "reconnect": False}
    st.lent = None
    session.power = None  # the reset or HiZ switches the supply off
    to = lent["to"]
    try:
        if lent["kind"] == LEGACY:
            reset = session.run(lambda bp: _reclaim_legacy(session, bp))
            session.disconnect()
            if reset:
                _wait_for_reset(session)
            return {"reclaimed": to, "reconnect": True}
        session.run(lambda bp: _reclaim_sump(session, bp))
        return {"reclaimed": to, "reconnect": False}
    except (BoardGone, NotConnected, BusPirateError, OSError) as exc:
        session.disconnect()
        return {"reclaimed": None, "reconnect": True,
                "warning": "could not take the board back from %s (%s)" % (to, exc)}
