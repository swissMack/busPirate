"""USB-PD plank (AP33772S): read the source's offers, ask it for one, hard reset.

The plank sits on the I2C bus and ``usbpd`` is an I2C-mode command, so all
three recipes run in ``m i2c -s 400``. ``usbpd-request`` changes the voltage
on the plank's output pins, so it needs its own yes.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple, Union

from ...bp6 import usbpd
from ...bp6.console import TerminalError
from . import Recipe, register
from .i2c import I2C_WIRING

Options = Dict[str, Any]

SOURCE = "https://docs.buspirate.com/docs/overview/usbpd-adapter/"
WORDS = ("usbpd", "usb-pd", "pd", "power delivery", "usb-c", "pps", "charger", "plank",
         "ap33772s")
NOTES = ("the plank's output can reach 28 V; hiz and the Bus Pirate's supply do not switch "
         "it off",)
RESET_NOTE = ("a reset power-cycles anything on the plank: VBUS drops to 0 V, then returns "
              "at 5 V")
CHANGE_HINT = ("the plank's output may have changed: measure the plank's output or run "
               "usbpd-reset before connecting anything to it")
#: The plank (AP33772S) takes at most 28 V, whatever a source offers (EPR goes to 48 V).
PLANK_MAX_MV = 28000
#: After a request that has not settled, ``usbpd status`` is read again up to
#: SETTLE_TRIES times, SETTLE_S apart, before the result is judged.
SETTLE_S = 0.5
SETTLE_TRIES = 3
NO_SOURCE_HINT = ("check that the USB-PD plank is fitted to the Bus Pirate and that a USB-C "
                  "PD source (a PD charger) is plugged into the plank, then re-run")


def _offer(pdo: Dict[str, Any]) -> str:
    volts = ("%d mV" % pdo["max_mv"] if pdo["type"] == "Fixed"
             else "%d-%d mV" % (pdo["min_mv"], pdo["max_mv"]))
    return "%d (%s %s, %s, up to %d mA)" % (pdo["index"], pdo["domain"], pdo["type"], volts,
                                            pdo["max_ma"])


def _status(con: Any) -> Union[Dict[str, Any], str]:
    """The status, or why the plank cannot be used."""
    try:
        st = usbpd.status(con)
    except TerminalError as exc:
        return str(exc)
    if st["source"] is None:
        return "the USB-PD plank did not answer 'usbpd status'"
    if st["source"] == "No source detected" or not st["pdos"]:
        return "%s: the plank sees no USB-PD offers" % st["source"]
    return st


def _check(con: Any, opts: Options) -> Dict[str, Any]:
    st = _status(con)
    if isinstance(st, str):
        return {"ok": False, "error": st, "hint": NO_SOURCE_HINT}
    return {"ok": True, "identity": "|".join(st["pdo_lines"]), "source": st["source"]}


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _resolve(st: Dict[str, Any], opts: Options) -> Union[str, Tuple[Dict[str, Any], int, int]]:
    """The chosen PDO, the voltage and the current to ask for, or why not."""
    pdos = {p["index"]: p for p in st["pdos"]}
    pdo = pdos.get(opts.get("pdo")) if _whole(opts.get("pdo")) else None
    if pdo is None:
        return ("pdo must be the number of one of the source's offers, not %r; it offers %s"
                % (opts.get("pdo"), "; ".join(_offer(p) for p in st["pdos"])))
    mv = opts.get("pd_mv")
    if pdo["type"] == "Fixed":
        if mv is not None and mv != pdo["max_mv"]:
            return ("pd_mv: PDO %d is a fixed %d mV offer and is always requested at that "
                    "voltage; leave pd_mv out, not %r" % (pdo["index"], pdo["max_mv"], mv))
        mv = pdo["max_mv"]
    elif not _whole(mv) or not pdo["min_mv"] <= mv <= pdo["max_mv"]:
        return ("pd_mv: PDO %d is a %s range, so give pd_mv in mV from %d to %d, not %r"
                % (pdo["index"], pdo["type"], pdo["min_mv"], pdo["max_mv"], mv))
    if mv > PLANK_MAX_MV:
        return ("pd_mv: the USB-PD plank takes at most %d mV, not %d"
                % (PLANK_MAX_MV, mv))
    ma = opts.get("pd_ma")
    if ma is None:
        ma = pdo["max_ma"]
    elif not _whole(ma) or not pdo["min_ma"] <= ma <= pdo["max_ma"]:
        return ("pd_ma: PDO %d allows %d to %d mA, not %r"
                % (pdo["index"], pdo["min_ma"], pdo["max_ma"], ma))
    return pdo, mv, ma


def _request_check(con: Any, opts: Options) -> Dict[str, Any]:
    st = _status(con)
    if isinstance(st, str):
        return {"ok": False, "error": st, "hint": NO_SOURCE_HINT}
    chosen = _resolve(st, opts)
    if isinstance(chosen, str):
        return {"ok": False, "error": chosen,
                "hint": "fix the options and plan again; nothing was requested"}
    return {"ok": True, "identity": "|".join(st["pdo_lines"]), "source": st["source"]}


def _read(con: Any, opts: Options) -> Dict[str, Any]:
    st = usbpd.status(con)
    st.pop("pdo_lines", None)
    return st


def _prepare(con: Any, opts: Options) -> Dict[str, Any]:
    """Only works out the request; ``_commit`` sends it."""
    chosen = _resolve(usbpd.status(con), opts)
    if isinstance(chosen, str):  # the check passed a moment ago, so this is unexpected
        raise TerminalError(chosen)
    pdo, mv, ma = chosen
    summary = ("Ask the USB-PD source for %d mV at up to %d mA (PDO %d, %s %s). The plank's "
               "output pins carry this voltage until usbpd-reset or the source is unplugged; "
               "hiz does not change it." % (mv, ma, pdo["index"], pdo["domain"], pdo["type"]))
    send_mv = None if pdo["type"] == "Fixed" else mv  # type: Optional[int]
    return {"chip": "USB-PD source", "operation": "request", "start": pdo["index"],
            "length": 0, "summary": summary, "backup": None,
            "_mv": mv, "_ma": ma, "_send_mv": send_mv}


def _near(value: Optional[int], mv: int) -> bool:
    return value is not None and abs(value - mv) <= max(500, mv // 20)


def _commit(con: Any, opts: Options, prepared: Dict[str, Any]) -> Dict[str, Any]:
    """Send the request, then judge it only once VBUS has settled.

    A ``rejected`` or ``failed`` answer changed nothing. Otherwise (``accepted``,
    or ``pending``/``unknown`` when the firmware's 2 s wait ran out) the request
    is done once the plank's requested voltage and VBUS are both at the target;
    until then ``usbpd status`` is read again. Still unsettled after that, the
    source may be moving to the new voltage, so the result says
    ``may_have_changed`` (the engine reports ``committed`` None, not False).
    """
    mv = prepared["_mv"]
    out = usbpd.request(con, prepared["start"], prepared["_send_mv"], prepared["_ma"])
    if out["result"] in ("rejected", "failed"):
        out["verified"] = False
        out["hint"] = ("the source answered '%s', so the request was not made; VBUS reads "
                       "%s mV" % (out["result"], out["vbus_mv"]))
        return out
    rereads = 0
    while not ((out["accepted"] or _near(out["requested_mv"], mv))
               and _near(out["vbus_mv"], mv)) and rereads < SETTLE_TRIES:
        time.sleep(SETTLE_S)
        st = usbpd.status(con)
        rereads += 1
        for key in ("vbus_mv", "vbus_ma", "requested_mv", "requested_ma"):
            out[key] = st[key]
    out["rereads"] = rereads
    out["verified"] = bool((out["accepted"] or _near(out["requested_mv"], mv))
                           and _near(out["vbus_mv"], mv))
    if not out["verified"]:
        out["may_have_changed"] = True
        out["hint"] = ("the source answered '%s' and VBUS still reads %s mV, not %d mV, "
                       "after %d re-reads: the plank's output may now be at %d mV or moving "
                       "there" % (out["result"], out["vbus_mv"], mv, rereads, mv))
    return out


def _reset(con: Any, opts: Options) -> Dict[str, Any]:
    return usbpd.reset(con)


_COMMON = dict(bus="i2c", transport="terminal", terminal_mode="i2c", terminal_flags="-s 400",
               default_mv=3300, min_mv=3000, max_mv=3600, milliamps=100, pullups=True,
               wiring=I2C_WIRING, source=SOURCE, notes=NOTES, words=WORDS)  # type: Dict[str, Any]

register(Recipe(
    name="usbpd-status", title="USB-PD plank: read the source's offers and the VBUS measurements",
    options={}, check=_check, action=_read, **_COMMON))

register(Recipe(
    name="usbpd-request", title="USB-PD plank: ask the source for one of its offers (a voltage)",
    risk="destructive", options={"pdo": None, "pd_mv": None, "pd_ma": None},
    check=_request_check, action=_prepare, commit=_commit,
    change_lines=("usbpd request",), change_hint=CHANGE_HINT, **_COMMON))

register(Recipe(
    name="usbpd-reset", title="USB-PD plank: send a PD hard reset (the source drops to 5 V)",
    options={}, check=_check, action=_reset,
    **dict(_COMMON, notes=NOTES + (RESET_NOTE,))))
