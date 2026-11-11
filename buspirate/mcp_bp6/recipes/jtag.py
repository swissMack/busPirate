"""JTAG and SWD pin finding with blueTag, through the terminal."""

from __future__ import annotations

from typing import Any, Dict

from ...bp6 import bluetag
from . import register, Recipe

DOCS = "https://docs.buspirate.com/docs/"
Options = Dict[str, Any]


def _check(protocol: str):
    def check(con: Any, opts: Options) -> Dict[str, Any]:
        try:
            bluetag.check_channels(protocol, opts["channels"])
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}
    return check


def _action(protocol: str):
    def action(con: Any, opts: Options) -> Dict[str, Any]:
        return bluetag.scan(con, protocol, opts["channels"], bool(opts.get("pulsing", True)))
    return action


_WIRING = tuple(("a candidate pad (any order)", "IO%d" % n) for n in range(8)) + (
    ("GND", "GND"), ("VREF", "VOUT"))
_NOTES = ("blueTag pulses the pins and can disturb a running target",
          "put each IO wire on a separate candidate pad of the suspected header; the order "
          "does not matter, blueTag finds which pad is which",
          "the scan cannot be interrupted and can take a minute or more")

for _proto, _title, _default in (("jtag", "JTAG", 6), ("swd", "SWD", 4)):
    register(Recipe(
        name="%s-pinout" % _proto, title="Find the %s pins of a target with blueTag" % _title,
        words=(_proto, "pinout", "pins", "find", "bluetag", "debug", "idcode"),
        bus="jtag", transport="terminal", terminal_mode="jtag", default_mv=3300, min_mv=1200,
        max_mv=5000, milliamps=100, pullups=False, wiring=_WIRING,
        check=_check(_proto), action=_action(_proto),
        options={"channels": _default, "pulsing": True}, notes=_NOTES,
        source=DOCS + "command-reference/"))
