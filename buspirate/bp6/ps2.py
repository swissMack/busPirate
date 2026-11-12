"""Parser and listener for the terminal's PS/2 ``sniff`` (pico-ps2-sniffer).

The firmware switches the supply on by itself (5.0 V, 400 mA, with pull-ups to
5 V) before it prints anything, and leaves it on until the mode is left.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from .console import Console, TerminalError

MAX_PACKETS = 200
MILLIVOLTS = 5000
MILLIAMPS = 400
_PACKET = re.compile(r"\[0x([0-9A-Fa-f]{4})\] t:0x([0-9A-Fa-f]{8}) ([DH]):0x([0-9A-Fa-f]{2})")
_ENTRY = re.compile(r"([A-Z][A-Z0-9_]*)(?: -->.*)?")
_TYPED = re.compile(r"key break tracker \(limit 0x[0-9A-Fa-f]+ bytes\): ([^\r\n]*)")
_DROPPED = re.compile(r"ring buffer full, (\d+) packet\(s\) dropped")
_PSU_ERROR = re.compile(r"PSU ERROR CODE[^\r\n]*")


def parse(text: str) -> Dict[str, Any]:
    packets = []  # type: List[Dict[str, Any]]
    keys = []  # type: List[str]
    after_packet = False
    for line in text.replace("\r", "\n").split("\n"):
        line = line.strip()
        found = _PACKET.search(line)
        if found:
            packets.append({"index": int(found.group(1), 16), "ms": int(found.group(2), 16),
                            "from": "keyboard" if found.group(3) == "D" else "host",
                            "byte": found.group(4).upper()})
            after_packet = True
            continue
        entry = _ENTRY.fullmatch(line) if after_packet else None
        if entry:
            keys.append(entry.group(1))
        if line:
            after_packet = False
    typed = _TYPED.findall(text)
    return {"packets": packets, "keys": keys, "typed": typed[-1] if typed else "",
            "dropped": sum(int(n) for n in _DROPPED.findall(text))}


#: What the firmware switches on by itself before sniffing.
SUPPLY = {"millivolts": MILLIVOLTS, "milliamps": MILLIAMPS, "on": True}


def listen(con: Console, seconds: float,
           on_supply: Optional[Callable[[Optional[Dict[str, Any]]], None]] = None
           ) -> Dict[str, Any]:
    """Sniff for ``seconds``. ``on_supply`` hears what became of the supply
    (``SUPPLY``, or None when the firmware could not switch it on) before
    anything that could raise, so the caller can record it either way."""
    tell = on_supply or (lambda supply: None)
    try:
        reply = con.listen("sniff", seconds, "q", ready="Sniffing...")
    except TerminalError as exc:
        # The firmware enables the supply before the banner: unless it said it
        # could not, count it as on (hiz switches it off either way).
        tell(None if "PSU ERROR CODE" in str(exc) else dict(SUPPLY))
        raise
    text = reply.text
    error = _PSU_ERROR.search(text)
    if error:
        tell(None)
        raise TerminalError("sniff failed: %s" % error.group(0).strip())
    supply = None
    if "PSU 5v Enabled" in text:
        supply = dict(SUPPLY)
        tell(dict(SUPPLY))  # before anything below that could raise
    if reply.error:
        raise TerminalError("sniff failed: %s" % reply.error)
    out = parse(text)
    count = len(out["packets"])
    out.update(packets=out["packets"][:MAX_PACKETS], count=count,
               truncated=count > MAX_PACKETS, seconds=seconds, supply=supply)
    return out
