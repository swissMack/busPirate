"""Hand-offs: lend the Bus Pirate 6 to flashrom, avrdude or PulseView.

Each runs in the terminal, in HiZ. It checks the ``binmode`` menu numbers,
marks the board lent and closes the BPIO2 port, then switches the second
port to the program's binary mode: Legacy (``binmode 5``) for flashrom and
avrdude, SUMP (``binmode 1``) for PulseView. The firmware itself switches
the supply on, so the engine sends no ``W`` (research doc section 8).
"""

from __future__ import annotations

import re
from typing import Any, Dict

from ...bp6.console import Answer, TerminalError
from ...mcp import power
from .. import handoff as lending
from . import Recipe, register
from .spi import SPI_WIRING

DOCS = "https://docs.buspirate.com/docs/"
Options = Dict[str, Any]
MILLIAMPS = 100
#: Legacy's prompts (research doc section 8), each with a short wait for the
#: whole question to arrive before it is answered.
OUTPUTS = "Set OUTPUT HOLD(IO2) & WP(IO3) pins?"
HOLD_HIGH = "Set HOLD HIGH?"
WP_HIGH = "Set WP HIGH?"
CLOCK = "Clock on IO0"
VOLTS = "Volts (0.80V-5.00V)"
CURRENT = "Maximum current (0mA-500mA)"
DONE = "Done! Just execute flashrom or avrdude"
_SET = re.compile(r"Power supply set to (\d+\.\d+)V, *(\d+)mA")
_WAIT = 0.05
LEGACY_REFUSAL = ("Legacy mode always switches the Bus Pirate's supply on; switch the "
                  "target's own supply off first")
SUMP_REFUSAL = ("SUMP mode switches the Bus Pirate's 3.3 V supply on when PulseView opens "
                "the port; switch the target's own supply off first")
SUMP_WARNING = ("the Bus Pirate switches its own 3.3 V supply on (100 mA) when PulseView "
                "opens the port")
SUMP_DRIVER = "Openbench Logic Sniffer & SUMP compatible"
_PART = re.compile(r"^[A-Za-z0-9_]+$")
STILL_LENT = "; the board is still lent: call connect or hiz to reset it"


def _mv(opts: Options) -> int:
    return int(opts.get("millivolts", 3300))


def _flashrom_check(con: Any, opts: Options) -> Dict[str, Any]:
    return {"ok": True}


def _avrdude_check(con: Any, opts: Options) -> Dict[str, Any]:
    part = opts.get("part")
    if not isinstance(part, str) or not _PART.match(part):
        return {"ok": False, "error": "part must be an avrdude part name such as m328p, "
                "not %r" % (part,)}
    return {"ok": True}


def _legacy(con: Any, to: str, opts: Options, outputs: bool) -> Dict[str, Any]:
    """Lend the board in Legacy mode; ``outputs`` drives HOLD and WP high."""
    session = con.session
    mv = _mv(opts)
    lending.check_menu(con, 5)
    out = lending.lend(session, session.board, to)
    answers = [Answer(OUTPUTS, "y" if outputs else "n", _WAIT)]
    if outputs:
        answers += [Answer(HOLD_HIGH, "y", _WAIT), Answer(WP_HIGH, "y", _WAIT)]
    answers += [Answer(CLOCK, "n", _WAIT), Answer(VOLTS, "%.2f" % (mv / 1000.0), _WAIT),
                Answer(CURRENT, "%d" % MILLIAMPS, _WAIT)]
    planned = power.plan_power("bp6", mv, power.SOURCE_OWNER, False, MILLIAMPS)
    try:
        reply = con.command("binmode 5", timeout=5.0, answers=answers, until=DONE)
    except TerminalError as exc:
        # The prompts may have got as far as the supply: count it as on until
        # the hand-back resets the board.
        session.power = planned
        raise TerminalError(str(exc) + STILL_LENT) from exc
    if reply.error:
        session.power = planned
        raise TerminalError("binmode 5 failed: %s%s" % (reply.error, STILL_LENT))
    match = _SET.search(reply.text)
    if match is None:
        session.power = planned
        raise TerminalError("Legacy mode did not report the supply it set%s" % STILL_LENT)
    got_mv, got_ma = int(round(float(match.group(1)) * 1000)), int(match.group(2))
    if (got_mv, got_ma) != (mv, MILLIAMPS):
        # The supply is on, but not at the plan: record what the firmware set.
        try:
            session.power = power.plan_power("bp6", got_mv, power.SOURCE_OWNER, False, got_ma)
        except (power.PowerRefused, ValueError):
            session.power = planned
        raise TerminalError("Legacy mode set the supply to %d mV, %d mA, not the planned "
                            "%d mV, %d mA%s" % (got_mv, got_ma, mv, MILLIAMPS, STILL_LENT))
    # The firmware switched the supply on at the plan: record it, so status
    # and the hand-back know it is on.
    session.power = planned
    out["supply"] = {"millivolts": mv, "milliamps": MILLIAMPS, "on": True}
    return out


def _flashrom_action(con: Any, opts: Options) -> Dict[str, Any]:
    """Lend the board to flashrom (Legacy binary mode), HOLD and WP driven high."""
    out = _legacy(con, "flashrom", opts, outputs=True)
    out["command"] = ("flashrom -p buspirate_spi:dev=%s,serialspeed=115200,spispeed=1M "
                      "-r backup.bin" % out["binary_port"])
    return out


def _avrdude_action(con: Any, opts: Options) -> Dict[str, Any]:
    """Lend the board to avrdude (Legacy binary mode), IO2 and IO3 left as inputs."""
    out = _legacy(con, "avrdude", opts, outputs=False)
    out["command"] = "avrdude -c buspirate -P %s -p %s" % (out["binary_port"], opts["part"])
    return out


def _pulseview_action(con: Any, opts: Options) -> Dict[str, Any]:
    """Lend the board to PulseView (SUMP logic analyzer on the second port)."""
    session = con.session
    lending.check_menu(con, 1)
    out = lending.lend(session, session.board, "pulseview")
    try:
        reply = con.command("binmode 1", answers=[Answer(lending.SAVE, "n", _WAIT)])
    except TerminalError as exc:
        raise TerminalError(str(exc) + STILL_LENT) from exc
    if reply.error:
        raise TerminalError("binmode 1 failed: %s%s" % (reply.error, STILL_LENT))
    out.update(driver=SUMP_DRIVER, serial_port=out["binary_port"],
               supply={"millivolts": 3300, "milliamps": MILLIAMPS,
                       "on": "while PulseView has the port open"})
    return out


_COMMON = dict(transport="terminal", terminal_mode=None, supply_by="action",
               target_powered_ok=False, default_mv=3300, milliamps=MILLIAMPS, pullups=False,
               source=DOCS + "command-reference/")

register(Recipe(
    name="flashrom", title="Hand the board to flashrom to read or write an SPI flash",
    words=("flashrom", "spi", "flash", "bios", "handoff", "legacy", "dump"), bus="spi",
    min_mv=1650, max_mv=3600, wiring=SPI_WIRING, check=_flashrom_check,
    action=_flashrom_action, options={}, target_powered_error=LEGACY_REFUSAL,
    notes=("Legacy mode switches the BP6's supply on at 3.3 V (100 mA) unless the plan names "
           "another voltage; a chip with its own power supply is refused",
           "Legacy mode drives HOLD (IO2) and WP (IO3) high; wire them to the chip if its "
           "HOLD and WP pins are not tied high",
           "the command reads the chip into backup.bin; anything else flashrom does is "
           "between the owner and flashrom"),
    **_COMMON))

register(Recipe(
    name="avrdude", title="Hand the board to avrdude to program an AVR over ISP",
    words=("avrdude", "avr", "atmega", "attiny", "isp", "arduino", "handoff", "legacy"),
    bus="spi", min_mv=1800, max_mv=5000,
    wiring=(("SCK", "IO6"), ("MOSI", "IO7"), ("MISO", "IO4"), ("RESET", "IO5"),
            ("GND", "GND"), ("VCC", "VOUT")),
    check=_avrdude_check, action=_avrdude_action, options={"part": "m328p"},
    target_powered_error=LEGACY_REFUSAL,
    notes=("Legacy mode switches the BP6's supply on at 3.3 V (100 mA) unless the plan names "
           "another voltage, up to 5 V; a target with its own power supply is refused",),
    **_COMMON))

register(Recipe(
    name="pulseview", title="Hand the board to PulseView as a logic analyzer",
    words=("pulseview", "sigrok", "logic", "analyzer", "sump", "capture", "handoff"),
    bus="pins", min_mv=3300, max_mv=3300,
    wiring=tuple(("a signal to watch", "IO%d" % n) for n in range(8)) + (("GND", "GND"),),
    check=_flashrom_check, action=_pulseview_action, options={},
    target_powered_error=SUMP_REFUSAL, notes=(SUMP_WARNING,), **_COMMON))
