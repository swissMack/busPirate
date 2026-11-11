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
#: How long ``q`` and ``y`` may take to bring the reset message.
EXIT_TIMEOUT_S = 5.0
STUCK = ("the Bus Pirate did not confirm that it left Legacy mode (%s), so it is "
         "still lent to %s, possibly with its supply on. Call connect or hiz again, or press "
         "the board's button to reset it")
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


def _ports_vanished(session: Any) -> bool:
    """Wait up to ``GONE_WAIT_S`` for the board's ports to vanish (a reset)."""
    deadline = time.monotonic() + GONE_WAIT_S
    while session.candidates():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _wait_for_return(session: Any) -> None:
    deadline = time.monotonic() + BACK_WAIT_S
    while time.monotonic() < deadline and not session.candidates():
        time.sleep(0.1)


def _reclaim_legacy(bp: Any) -> bool:
    """``q`` then ``y`` on the locked terminal.

    True once the board says it is resetting; False if a main prompt came
    back instead (the terminal is not locked, so Legacy is not running: the
    board reset earlier). Raises ``TerminalError`` if neither happened.
    """
    with bp.raw_console() as con:
        reply = con.command("q", timeout=EXIT_TIMEOUT_S, until=RESETTING,
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


def _released(session: Any, lent: Dict[str, Any], reconnect: bool,
              warning: str = "") -> Dict[str, Any]:
    """The board is no longer lent: forget it, and its supply (reset or HiZ is off)."""
    state.of(session).lent = None
    session.power = None
    out = {"reclaimed": lent["to"] if not warning else None,
           "reconnect": reconnect}  # type: Dict[str, Any]
    if warning:
        out["warning"] = warning
    return out


def _unreachable(session: Any, lent: Dict[str, Any], exc: BaseException) -> Dict[str, Any]:
    """The board cannot be reached (unplugged): nothing is lent any more."""
    session.disconnect()
    return _released(session, lent, True, "could not take the board back from %s (%s)"
                     % (lent["to"], exc))


def reclaim(session: Any) -> Dict[str, Any]:
    """Take a lent board back.

    ``reconnect`` True means the session was dropped (the board reset, or
    could not be reached) and the caller should connect again. A Legacy
    board that answered but never confirmed its reset stays lent, with its
    supply counted as on, and the result carries ``error``.
    """
    lent = state.of(session).lent
    if lent is None:
        return {"reclaimed": None, "reconnect": False}
    to = lent["to"]
    if lent["kind"] == SUMP:
        try:
            session.run(lambda bp: _reclaim_sump(session, bp))
        except (BoardGone, NotConnected, BusPirateError, OSError) as exc:
            # A fresh connect selects BPIO2 through the terminal, so SUMP
            # needs no confirmation.
            return _unreachable(session, lent, exc)
        return _released(session, lent, False)
    try:
        reset = session.run(_reclaim_legacy)
    except (BoardGone, NotConnected) as exc:
        return _unreachable(session, lent, exc)
    except (BusPirateError, OSError) as exc:
        if not _ports_vanished(session):
            return {"reclaimed": None, "reconnect": False,
                    "error": STUCK % (exc, to)}
        reset = True  # the ports went away: the board did reset
    session.disconnect()
    if reset:
        _wait_for_return(session)
    return _released(session, lent, True)
