"""Sniffers: listen to an I2C or 2WIRE bus without driving it."""

from __future__ import annotations

from typing import Any, Dict

from ...bp6 import ps2, sniff
from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
Options = Dict[str, Any]


def _check(con: Any, opts: Options) -> Dict[str, Any]:
    s = opts.get("seconds")
    if isinstance(s, bool) or not isinstance(s, (int, float)) or not 0 < s <= 60:
        return {"ok": False, "error": "seconds must be a number above 0 and at most 60, not %r" % (s,)}
    return {"ok": True}


def _i2c_action(con: Any, opts: Options) -> Dict[str, Any]:
    return sniff.listen_i2c(con, float(opts["seconds"]))


def _2wire_action(con: Any, opts: Options) -> Dict[str, Any]:
    return sniff.listen_2wire(con, float(opts["seconds"]))


_WIRING = (("SDA / data", "IO0"), ("SCL / clock", "IO1"), ("GND", "GND"),
           ("target VCC", "VOUT"))
_COMMON = dict(bus="pins", transport="terminal", risk="none", pullups=False, default_mv=0,
               min_mv=1800, max_mv=5000, milliamps=100, options={"seconds": 5},
               terminal_flags="-s 400", check=_check, wiring=_WIRING,
               source=DOCS + "command-reference/")

register(Recipe(
    name="i2c-sniff", title="Sniff I2C: listen to the traffic between a controller and a chip",
    words=("i2c-sniff", "sniff", "sniffer", "i2c", "bus", "traffic", "monitor", "spy"),
    terminal_mode="i2c", action=_i2c_action,
    notes=("IO2 and IO3 are driven by the sniffer: leave them unconnected",
           "listens only: the bus's own pull-ups and supply are used",
           "up to about 500 kHz; on a very busy bus some bytes can be lost without warning"),
    **{**_COMMON, "bus": "i2c"}))

register(Recipe(
    name="2wire-sniff", title="Sniff 2WIRE: listen to a two-wire smart-card or SLE4442 bus",
    words=("2wire-sniff", "2wire", "sle4442", "smart card", "sniff", "sniffer"),
    terminal_mode="2wire", action=_2wire_action,
    notes=("IO2 and IO3 are driven by the sniffer: leave them unconnected (IO2 is also "
           "2WIRE's RST)",
           "no ACK bits on this bus"),
    **_COMMON))


def _ps2_action(con: Any, opts: Options) -> Dict[str, Any]:
    return ps2.listen(con, float(opts["seconds"]))


register(Recipe(
    name="ps2-sniff", title="Sniff PS/2: record what is typed on a keyboard you own",
    words=("ps2", "ps/2", "keyboard", "sniff", "sniffer", "keylogger", "mouse"),
    bus="pins", transport="terminal", terminal_mode="ps2", risk="owner-only",
    supply_by="action", pullups=False, default_mv=5000, min_mv=5000, max_mv=5000,
    milliamps=400, target_powered_ok=False, options={"seconds": 10}, check=_check,
    action=_ps2_action,
    target_powered_error=("VOUT reads a voltage: the PS/2 sniffer drives VOUT to 5 V itself, "
                          "so leave VOUT unconnected (the keyboard keeps its own supply from "
                          "the computer)"),
    wiring=(("keyboard DATA", "IO4"), ("keyboard CLOCK", "IO5"), ("GND", "GND")),
    notes=("the sniffer switches the Bus Pirate's supply on at 5.0 V (400 mA) and the "
           "pull-ups to 5 V by itself; it stays on until hiz",
           "leave VOUT, IO6 and IO7 unconnected; IO6 and IO7 are driven by the sniffer",
           "only for a keyboard you own: everything typed on it is recorded"),
    source=DOCS + "command-reference/"))
