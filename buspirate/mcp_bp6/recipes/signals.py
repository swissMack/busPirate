"""PWM output and frequency measurement on the IO pins, through the terminal."""

from __future__ import annotations

from typing import Any, Dict

from ...bp6 import signals
from .. import state
from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
Options = Dict[str, Any]


def _pwm_pins(con: Any) -> set:
    return state.of(con.session).pwm_pins


def _shared(pin: int, pwm_pins: set) -> Any:
    """The running PWM pin that shares ``pin``'s slice, or None."""
    return next((p for p in sorted(pwm_pins) if p // 2 == pin // 2), None)


def _pwm_check(con: Any, opts: Options) -> Dict[str, Any]:
    try:
        signals.check_pwm(opts["pin"], opts["hz"], opts["duty"])
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    pin = opts["pin"]
    other = _shared(pin, _pwm_pins(con))
    if other is not None:
        pair = "IO%d and IO%d" % (pin - pin % 2, pin - pin % 2 + 1)
        return {"ok": False, "error": "%s share one PWM, and IO%d already has one running; "
                "stop it with pwm_off (or hiz) first" % (pair, other)}
    return {"ok": True}


def _pwm_action(con: Any, opts: Options) -> Dict[str, Any]:
    out = signals.pwm_start(con, opts["pin"], opts["hz"], opts["duty"])
    _pwm_pins(con).add(opts["pin"])
    return out


def _freq_check(con: Any, opts: Options) -> Dict[str, Any]:
    try:
        signals.check_frequency_pin(opts["pin"])
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    other = _shared(opts["pin"], _pwm_pins(con))
    if other is not None:
        return {"ok": False, "error": "IO%d shares a PWM with IO%d, which is generating a "
                "signal; stop it with pwm_off first" % (opts["pin"], other)}
    return {"ok": True}


def _freq_action(con: Any, opts: Options) -> Dict[str, Any]:
    return signals.measure_frequency(con, opts["pin"])


_COMMON = dict(bus="pins", transport="terminal", terminal_mode="dio", default_mv=3300,
               min_mv=1200, max_mv=5000, milliamps=100, pullups=False,
               source=DOCS + "command-reference/")

register(Recipe(
    name="pwm-signal", title="PWM: a square wave of a chosen frequency and duty cycle",
    words=("pwm", "square", "wave", "frequency", "clock", "duty", "signal", "generate"),
    wiring=(("GND", "GND"), ("signal in", "IO pin from the pin option (default IO0)")),
    check=_pwm_check, action=_pwm_action,
    options={"pin": 0, "hz": 1000, "duty": 50},
    notes=("8 Hz to 62.5 MHz; IO0/IO1, IO2/IO3, IO4/IO5 and IO6/IO7 each share one PWM, so "
           "only one pin of a pair can generate",
           "the signal keeps running until pwm_off or hiz"),
    **_COMMON))

register(Recipe(
    name="frequency-measure", title="Frequency and duty cycle of a signal on an IO pin",
    words=("frequency", "measure", "counter", "hertz", "duty", "signal", "clock"),
    wiring=(("GND", "GND"), ("signal out", "IO1, IO3, IO5 or IO7 (the pin option)")),
    check=_freq_check, action=_freq_action, options={"pin": 1},
    notes=("only IO1, IO3, IO5 and IO7 can measure",),
    **_COMMON))
