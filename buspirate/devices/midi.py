"""Decode a MIDI byte stream (31250 baud 8N1): channel messages, SysEx and real-time bytes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

DEVICES: list = []

_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_REALTIME = {0xF8: "clock_ticks", 0xFE: "active_sensing"}
_OTHER_REALTIME = (0xFA, 0xFB, 0xFC, 0xFF)
#: Data bytes each channel message type takes.
_LENGTH = {0x8: 2, 0x9: 2, 0xA: 2, 0xB: 2, 0xC: 1, 0xD: 1, 0xE: 2}


def note_name(number: int) -> str:
    """60 -> C4, 21 -> A0 (middle C is C4)."""
    return "%s%d" % (_NAMES[number % 12], number // 12 - 1)


def _message(status: int, d: List[int]) -> Dict[str, Any]:
    kind, channel = status >> 4, (status & 0x0F) + 1
    if kind in (0x8, 0x9):
        off = kind == 0x8 or d[1] == 0
        return {"type": "note off" if off else "note on", "channel": channel,
                "note": note_name(d[0]), "number": d[0], "velocity": d[1]}
    if kind == 0xA:
        return {"type": "aftertouch", "channel": channel, "note": note_name(d[0]),
                "number": d[0], "pressure": d[1]}
    if kind == 0xB:
        return {"type": "control change", "channel": channel, "controller": d[0],
                "value": d[1]}
    if kind == 0xC:
        return {"type": "program change", "channel": channel, "program": d[0]}
    if kind == 0xD:
        return {"type": "channel pressure", "channel": channel, "pressure": d[0]}
    return {"type": "pitch bend", "channel": channel, "value": (d[1] << 7 | d[0]) - 8192}


def parse(data: bytes) -> Dict[str, Any]:
    out: Dict[str, Any] = {"messages": [], "clock_ticks": 0, "active_sensing": 0,
                           "other_realtime": 0}
    status: Optional[int] = None
    pending: List[int] = []
    sysex: Optional[int] = None  # data bytes seen so far inside a SysEx
    for b in data:
        if b >= 0xF8:  # real-time: legal anywhere, never disturbs a message
            if b in _REALTIME:
                out[_REALTIME[b]] += 1
            else:
                out["other_realtime"] += 1
            continue
        if b == 0xF0:
            sysex, status, pending = 0, None, []
        elif b == 0xF7:
            if sysex is not None:
                out["messages"].append({"type": "sysex", "channel": None, "length": sysex})
            sysex = None
        elif b >= 0x80:
            sysex = None
            pending = []
            status = b if b < 0xF0 else None  # system common clears running status
        elif sysex is not None:
            sysex += 1
        elif status is not None:
            pending.append(b)
            if len(pending) == _LENGTH[status >> 4]:
                out["messages"].append(_message(status, pending))
                pending = []  # running status keeps `status`
    return out
