"""The board itself: the firmware's self-test (the terminal's ``~``)."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ...bp6.console import Answer
from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
Options = Dict[str, Any]

#: Any pin or VOUT above this means something is connected (the self-test drives the pins).
CONNECTED_MV = 300
BUTTON_MAX_S = 60
_ERRORS = re.compile(r"ERRORS:\s*(\d+)")


def _precheck(bp: Any, opts: Options) -> Dict[str, Any]:
    """Refuse to start while anything puts a voltage on the pins or on VOUT."""
    st = bp.status()
    live = ["IO%d" % i for i, mv in enumerate(st.adc_mv) if mv > CONNECTED_MV]
    if not st.psu_enabled and st.psu_mv > CONNECTED_MV:
        live.append("VOUT")
    if live:
        return {"ok": False, "error": "%s reads above %d mV: disconnect everything from the "
                "Bus Pirate's pins first" % (", ".join(live), CONNECTED_MV)}
    return {"ok": True}


def _check(con: Any, opts: Options) -> Dict[str, Any]:
    seconds = opts["button_s"]
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) \
            or not 0 <= seconds <= BUTTON_MAX_S:
        return {"ok": False, "error": "button_s is how many seconds to wait for the button, "
                "0 to %d, not %r" % (BUTTON_MAX_S, seconds)}
    return {"ok": True}


def _verdict(passed: bool, errors: List[str], skipped: bool, count: int) -> str:
    if passed:
        return "every test passed, including the button"
    if not errors:
        if skipped:
            return "every block passed; the button test was skipped"
        return "the self-test failed (%d errors) without naming a block" % count
    text = "%d block%s failed: %s" % (len(errors), "" if len(errors) == 1 else "s",
                                      "; ".join(errors))
    return text + ("; the button test was skipped" if skipped else "")


def _action(con: Any, opts: Options) -> Dict[str, Any]:
    """Run the firmware's self-test and report each failing line."""
    seconds = float(opts["button_s"])
    reply = con.command("~", timeout=60 + seconds, answers=[
        Answer("Format the Bus Pirate NAND flash", "n"),
        Answer("PUSH BUTTON (SPACE TO SKIP):", " ", wait_s=seconds)])
    con.session.power = None  # the firmware switches its supply off at the end
    text = reply.text
    lines = [ln.strip() for ln in text.splitlines()]
    skipped = any(ln == "SKIPPED" or ln.endswith("SKIPPED") for ln in lines)
    passed = "PASS :)" in lines and not skipped
    errors = [ln for ln in lines if "ERROR" in ln and not _ERRORS.match(ln)]
    found = next((int(m.group(1)) for m in map(_ERRORS.match, lines) if m), 0)
    return {"passed": passed, "errors": errors,
            "button": "skipped" if skipped else "pressed",
            "verdict": _verdict(passed, errors, skipped, found)}


register(Recipe(
    name="self-test", title="Self-test: the Bus Pirate checks its own pins, supply and button",
    words=("self", "test", "selftest", "check", "board", "health", "diagnose", "button"),
    wiring=(), check=_check, action=_action, precheck=_precheck,
    options={"button_s": 20}, bus="board", transport="terminal", terminal_mode=None,
    min_mv=0, max_mv=0, default_mv=0, milliamps=0, pullups=False, source=DOCS + "command-reference/",
    notes=("the self-test switches the Bus Pirate's own supply on at 3.3 V",
           "press the board's button (twice: press and release) within button_s seconds, "
           "or the button test is skipped and the run reports a failure",
           "disconnect everything from the pins first")))
