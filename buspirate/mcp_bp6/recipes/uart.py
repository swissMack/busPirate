"""UART recipes: a serial console and a GPS receiver. Usually the target has its own supply."""

from __future__ import annotations

from typing import Any, Dict

from ...devices import nmea
from ...mcp import jobs
from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
#: The Bus Pirate's TX drives the target's RX, and its RX listens to the target's TX.
UART_WIRING = (("RX", "IO4"), ("TX", "IO5"), ("GND", "GND"), ("VCC", "VOUT"))
UART_NOTES = ("cross the lines: BP6 TX (IO4) goes to the target's RX, and BP6 RX (IO5) to "
              "the target's TX",
              "a target with its own supply is the usual case: the Bus Pirate's supply stays "
              "off and VOUT only reads the target's voltage")
Options = Dict[str, Any]


def _validate(opts: Options) -> None:
    baud, seconds = opts["baud"], opts["seconds"]
    if isinstance(baud, bool) or baud not in jobs._BAUDS:
        raise ValueError("baud must be one of %s, not %r"
                         % (", ".join(str(b) for b in sorted(jobs._BAUDS)), baud))
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) \
            or not 0 < seconds <= 30:
        raise ValueError("seconds must be more than 0 and at most 30, not %r" % (seconds,))


def _check(bp: Any, opts: Options) -> Dict[str, Any]:
    try:
        _validate(opts)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def _listen(bp: Any, opts: Options) -> bytes:
    with bp.uart() as m:
        m.set_baudrate(jobs._baud_index(opts["baud"]))
        m.configure()  # 8N1
        return jobs._listen(bp, m, float(opts["seconds"]))


def _console_action(bp: Any, opts: Options) -> Dict[str, Any]:
    """Listen on the serial line and return what the target says."""
    data = _listen(bp, opts)
    return {"text": jobs._printable(data), "hex": data.hex(" "), "bytes": len(data),
            "seconds": opts["seconds"], "baud": opts["baud"]}


def _gps_action(bp: Any, opts: Options) -> Dict[str, Any]:
    """Listen for NMEA sentences and decode them (GGA and RMC)."""
    data = _listen(bp, opts)
    text = jobs._printable(data)
    sentences = nmea.parse(text)
    return {"text": text, "sentences": sentences, "count": len(sentences),
            "bytes": len(data), "seconds": opts["seconds"], "baud": opts["baud"]}


register(Recipe(
    name="uart-console", title="UART console: listen to a target's serial output",
    words=("uart-console", "uart", "serial", "console", "tty", "boot log", "rx", "tx"),
    bus="uart", default_mv=0, min_mv=1800, max_mv=5000, pullups=False, wiring=UART_WIRING,
    check=_check, action=_console_action, options={"baud": 115200, "seconds": 3},
    source=DOCS + "command-reference/", notes=UART_NOTES))

register(Recipe(
    name="gps", title="GPS receiver: read and decode its NMEA output",
    words=("gps", "nmea", "gnss", "position", "location"),
    bus="uart", default_mv=0, min_mv=1800, max_mv=5000, pullups=False, wiring=UART_WIRING,
    check=_check, action=_gps_action, options={"baud": 9600, "seconds": 3},
    source="https://github.com/swissMack/busPirate (buspirate/devices/nmea.py; "
           "not on docs.buspirate.com)", notes=UART_NOTES))
