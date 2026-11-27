"""Infrared: receive and decode remote-control codes, and send them."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from ...bp6 import infrared
from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
Options = Dict[str, Any]

_RX_PIN = {"38d": "IO5", "56d": "IO7", "38b": "IO3"}


def _int_in(value: Any, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _check_receive(con: Any, opts: Options) -> Dict[str, Any]:
    s = opts.get("seconds")
    if isinstance(s, bool) or not isinstance(s, (int, float)) or not 0 <= s <= 60:
        return {"ok": False, "error": "seconds must be a number from 0 to 60, not %r" % (s,)}
    if opts.get("sensor") not in infrared.SENSORS:
        return {"ok": False, "error": "sensor must be one of %s, not %r"
                % (", ".join(infrared.SENSORS), opts.get("sensor"))}
    return {"ok": True}


def _receive(con: Any, opts: Options) -> Dict[str, Any]:
    return infrared.receive(con, float(opts["seconds"]), opts["sensor"])


def _check_nec(con: Any, opts: Options) -> Dict[str, Any]:
    for key in ("address", "command"):
        if not _int_in(opts.get(key), 0, 255):
            return {"ok": False, "error": "NEC %s must be a whole number from 0 to 255, not %r"
                    % (key, opts.get(key))}
    return {"ok": True}


def _send_nec(con: Any, opts: Options) -> Dict[str, Any]:
    return infrared.send_code(con, opts["address"] << 8 | opts["command"])


def _check_rc5(con: Any, opts: Options) -> Dict[str, Any]:
    for key, high in (("address", 31), ("command", 63), ("toggle", 1)):
        if not _int_in(opts.get(key), 0, high):
            return {"ok": False, "error": "RC5 %s must be a whole number from 0 to %d, not %r"
                    % (key, high, opts.get(key))}
    return {"ok": True}


def _send_rc5(con: Any, opts: Options) -> Dict[str, Any]:
    """Send the code; ``tx`` is what the firmware echoed, with its start bits (0x3000) set."""
    return infrared.send_code(con, opts["toggle"] << 11 | opts["address"] << 6 | opts["command"])


def _check_raw(con: Any, opts: Options) -> Dict[str, Any]:
    problem = infrared.air_error(opts.get("air"))
    if problem:
        return {"ok": False, "error": problem}
    return {"ok": True}


def _send_raw(con: Any, opts: Options) -> Dict[str, Any]:
    return infrared.send_air(con, opts["air"])


_TX_WIRE = ("IR LED driver input", "IO4")
_TAIL = (("VCC", "VOUT"), ("GND", "GND"))


def _receive_wiring(opts: Options) -> Tuple[Tuple[str, str], ...]:
    pin = _RX_PIN.get(opts.get("sensor"), "IO5")
    return (("IR receiver OUT", pin), _TX_WIRE) + _TAIL


_COMMON = dict(bus="infrared", transport="terminal", terminal_mode="infrared", risk="none",
               pullups=False, default_mv=3300, min_mv=2700, max_mv=5000, milliamps=100,
               source=DOCS + "command-reference/")
_VOLTS = "VOUT powers the receiver and the LED driver at the planned voltage (3.3 V by default)"
_SEND_NOTES = (_VOLTS, "the LED on IO4 needs a transistor driver; the IR Toy plank has one",
               "leave IO0 unconnected: the receiver drives it internally")
_SEND_WIRING = _receive_wiring({"sensor": "38d"})
_SEND_WORDS = ("ir", "infrared", "remote", "send", "transmit", "blast")

register(Recipe(
    name="ir-receive", title="Receive IR: capture and decode the codes a remote control sends",
    words=("ir", "infrared", "remote", "receive", "learn", "decode", "nec", "rc5"),
    terminal_flags="-p raw -r 38k_demod", options={"seconds": 10, "sensor": "38d"},
    check=_check_receive, action=_receive, wiring=_receive_wiring({"sensor": "38d"}),
    wiring_for=_receive_wiring,
    notes=(_VOLTS, "leave IO0 unconnected: the receiver drives it internally",
           "the carrier frequency is measured only when a learner sensor is wired to IO1; "
           "without it the carrier reads 0 and the frame cannot be resent raw",
           "point the remote at the receiver from about 10 cm and press the button briefly"),
    **_COMMON))

register(Recipe(
    name="ir-send-nec", title="Send an IR code in the NEC protocol (address and command)",
    words=_SEND_WORDS + ("nec",), terminal_flags="-p nec",
    options={"address": None, "command": None}, check=_check_nec, action=_send_nec,
    wiring=_SEND_WIRING, notes=_SEND_NOTES, **_COMMON))

register(Recipe(
    name="ir-send-rc5", title="Send an IR code in the RC5 protocol (address, command, toggle)",
    words=_SEND_WORDS + ("rc5",), terminal_flags="-p rc5",
    options={"address": None, "command": None, "toggle": 0}, check=_check_rc5,
    action=_send_rc5, wiring=_SEND_WIRING, notes=_SEND_NOTES, **_COMMON))

register(Recipe(
    name="ir-send-raw", title="Send a raw IR packet (aIR text, such as one received earlier)",
    words=_SEND_WORDS + ("raw",), terminal_flags="-p raw -r 38k_demod", options={"air": None},
    check=_check_raw, action=_send_raw, wiring=_SEND_WIRING, notes=_SEND_NOTES, **_COMMON))
