"""Infrared codes: parse the Bus Pirate's aIR text, decode NEC and RC5, encode NEC."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

DEVICES: list = []

_FRAME = re.compile(r"\$(\d+):([0-9,\s]*?);")
_RC5_HALF = 889


def parse_air(text: str) -> List[Dict]:
    """One dict per ``$<khz>:<v>,<v>,...,;`` frame: carrier and mark/space durations (us)."""
    frames = []
    for match in _FRAME.finditer(text):
        values = [int(v) for v in re.findall(r"\d+", match.group(2))]
        frames.append({"carrier_khz": int(match.group(1)), "durations": values})
    return frames


def to_air(carrier_khz: int, durations: List[int]) -> str:
    """Format aIR for ``irtx``. No ';' (the terminal treats it as a command separator)."""
    if not 20 <= carrier_khz <= 60:
        raise ValueError("carrier must be 20-60 kHz, got %d" % carrier_khz)
    if (len(durations) + 1) // 2 > 127:
        raise ValueError("at most 127 mark/space pairs, got %d values" % len(durations))
    return "$%d:%s" % (carrier_khz, "".join("%d," % d for d in durations))


def encode_nec(address: int, command: int) -> List[int]:
    """Durations for one NEC frame (address and command 0-255, inverses added)."""
    if not (0 <= address <= 255 and 0 <= command <= 255):
        raise ValueError("NEC address and command must be 0-255")
    word = address | ((address ^ 0xFF) << 8) | (command << 16) | ((command ^ 0xFF) << 24)
    out = [9000, 4500]
    for i in range(32):
        out += [560, 1690 if (word >> i) & 1 else 560]
    out.append(560)
    return out


def _near(value: int, target: int, tol: float) -> bool:
    return abs(value - target) <= target * tol


def _decode_nec(d: List[int]) -> Optional[Dict]:
    if len(d) < 67 or not _near(d[0], 9000, 0.2) or not _near(d[1], 4500, 0.2):
        return None
    word = 0
    for i in range(32):
        mark, space = d[2 + 2 * i], d[3 + 2 * i]
        if not _near(mark, 560, 0.35):
            return None
        if _near(space, 1690, 0.35):
            word |= 1 << i
        elif not _near(space, 560, 0.35):
            return None
    addr, naddr = word & 0xFF, (word >> 8) & 0xFF
    cmd, ncmd = (word >> 16) & 0xFF, (word >> 24) & 0xFF
    if cmd ^ ncmd != 0xFF:
        return None
    if addr ^ naddr == 0xFF:
        return {"protocol": "nec", "address": addr, "command": cmd}
    return {"protocol": "nec", "address": addr | (naddr << 8), "command": cmd, "extended": True}


def _decode_rc5(d: List[int]) -> Optional[Dict]:
    halves = [0]  # the leading space of S1=1 is invisible in a received frame
    level = 1
    for v in d:
        if _near(v, _RC5_HALF, 0.35):
            n = 1
        elif _near(v, 2 * _RC5_HALF, 0.35):
            n = 2
        else:
            return None
        halves += [level] * n
        level ^= 1
    if len(halves) == 27:
        halves.append(0)  # the trailing space is omitted
    if len(halves) != 28:
        return None
    bits = []
    for i in range(0, 28, 2):
        pair = (halves[i], halves[i + 1])
        if pair == (0, 1):
            bits.append(1)
        elif pair == (1, 0):
            bits.append(0)
        else:
            return None
    if bits[0] != 1:
        return None
    s2, toggle = bits[1], bits[2]
    address = int("".join(map(str, bits[3:8])), 2)
    command = int("".join(map(str, bits[8:14])), 2)
    if not s2:
        command |= 64
    return {"protocol": "rc5", "address": address, "command": command, "toggle": toggle}


def decode(durations: List[int]) -> Optional[Dict]:
    """Decode one frame's mark/space durations as NEC or RC5; None if neither fits."""
    return _decode_nec(durations) or _decode_rc5(durations)
