"""PWM output and frequency measurement through the Bus Pirate 6's terminal.

``G`` asks for the frequency and the duty cycle as separate lines, so they are
answered, never passed as arguments. ``F`` (continuous measure) never ends by
itself and is never sent; ``f`` is always sent with a pin (a bare ``f``
switches a background measurement off). Strings are the firmware's own
(research doc sections 2 and 3).
"""

from __future__ import annotations

import re
from typing import Any, Dict

from .console import Answer, TerminalError

PWM_MIN_HZ = 8
PWM_MAX_HZ = 62_500_000
FREQ_PINS = (1, 3, 5, 7)

_ENABLED = "Generate frequency: Enabled on IO%d"
_ACTUAL_HZ = re.compile(r"Actual frequency: (\d+)Hz")
_ACTUAL_PERIOD = re.compile(r"Actual period: (\d+)ns")
_ACTUAL_DUTY = re.compile(r"Actual duty cycle: (\d+)ns")
_MEASURED = re.compile(r"Frequency IO(\d+):.*?\((\d+)Hz\), Duty cycle: ([0-9.]+)%")


def _pin(pin: Any) -> int:
    if isinstance(pin, bool) or not isinstance(pin, int) or not 0 <= pin <= 7:
        raise ValueError("pin must be a whole number from 0 to 7 (IO0 to IO7), not %r" % (pin,))
    return pin


def _number(value: float) -> str:
    """A plain decimal, never an exponent: the firmware's parser has no ``e``."""
    if float(value).is_integer():
        return str(int(value))
    return ("%.6f" % value).rstrip("0").rstrip(".")


def check_pwm(pin: Any, hz: Any, duty: Any) -> None:
    """Refuse a PWM request the firmware would re-prompt for; raises ValueError."""
    _pin(pin)
    for name, value in (("hz", hz), ("duty", duty)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("%s must be a number, not %r" % (name, value))
    if not PWM_MIN_HZ <= hz <= PWM_MAX_HZ:
        raise ValueError("hz must be %d to %d (8 Hz to 62.5 MHz), not %s"
                         % (PWM_MIN_HZ, PWM_MAX_HZ, _number(hz)))
    if not 0 < duty <= 100:
        raise ValueError("duty must be above 0 and at most 100 (percent), not %s" % _number(duty))


def check_frequency_pin(pin: Any) -> None:
    _pin(pin)
    if pin not in FREQ_PINS:
        raise ValueError("only IO1, IO3, IO5 and IO7 can measure frequency, not IO%d" % pin)


def pwm_start(con: Any, pin: int, hz: float, duty: float) -> Dict[str, Any]:
    """``G <pin>``, then the frequency and the duty cycle as the prompts ask."""
    check_pwm(pin, hz, duty)
    reply = con.command("G %d" % pin, answers=(
        Answer("Period or frequency", "%shz" % _number(hz)),
        Answer("Duty cycle (%)", "%s%%" % _number(duty))))
    if reply.error:
        raise TerminalError(reply.error)
    if _ENABLED % pin not in reply.text:
        raise TerminalError("the PWM on IO%d was not enabled: %s" % (pin, reply.text.strip()[-200:]))
    freq = _ACTUAL_HZ.search(reply.text)
    period = _ACTUAL_PERIOD.search(reply.text)
    width = _ACTUAL_DUTY.search(reply.text)
    actual_hz = int(freq.group(1)) if freq else hz
    if period and width and int(period.group(1)):
        actual_duty = int(width.group(1)) / int(period.group(1)) * 100
    else:
        actual_duty = duty
    return {"pin": pin, "actual_hz": actual_hz, "actual_duty_percent": round(actual_duty, 2)}


def pwm_stop(con: Any, pin: int) -> Dict[str, Any]:
    """``g <pin>``. Already off (or the board in HiZ, which has no PWM) is not an error."""
    _pin(pin)
    reply = con.command("g %d" % pin)
    if "Disabled on IO%d" % pin in reply.text:
        return {"pin": pin, "stopped": True}
    if "not active" in reply.text or "not active" in (reply.error or "") \
            or "HiZ" in (reply.error or ""):
        return {"pin": pin, "stopped": False, "note": "no PWM was running on IO%d" % pin}
    raise TerminalError(reply.error or "the PWM on IO%d did not stop: %s"
                        % (pin, reply.text.strip()[-200:]))


def measure_frequency(con: Any, pin: int) -> Dict[str, Any]:
    """One ``f <pin>`` reading: frequency in Hz and duty cycle in percent."""
    check_frequency_pin(pin)
    reply = con.command("f %d" % pin)
    if reply.error:
        raise TerminalError(reply.error)
    match = _MEASURED.search(reply.text)
    if match is None or int(match.group(1)) != pin:
        raise TerminalError("no frequency reading for IO%d: %s" % (pin, reply.text.strip()[-200:]))
    return {"pin": pin, "hz": int(match.group(2)), "duty_percent": float(match.group(3))}
