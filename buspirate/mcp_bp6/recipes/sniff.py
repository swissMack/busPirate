"""Sniffers: listen to an I2C or 2WIRE bus without driving it."""

from __future__ import annotations

from typing import Any, Dict

from ...bp6 import sniff
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
