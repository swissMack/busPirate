"""Character LCDs: an HD44780 behind a PCF8574 I2C "backpack" (0x27 / 0x3F).

The first *output* device in the catalog: rather than translating bytes
into meaning, it translates a message into bytes. :func:`compose` turns
plain text and a few plain-word commands into steps, and :func:`script`
writes them one step per line with the meaning as a comment:

    3c 38         # wake-up 1 of 3
    4d 49 8d 89   # 'H'

Sending (:func:`send`) writes each line as its own I2C transfer with a
pause after it, which is what the display's slow steps need — so a script
the user has edited by hand still keeps the timing.

The backpack wiring is the common one, proven on a 16x2 at 0x27:
P0 = RS, P1 = RW, P2 = E, P3 = backlight, P4–P7 = D4–D7. The address only
identifies the backpack; the display's size cannot be read over I2C.
"""

from __future__ import annotations

import re
import time
from typing import List, Tuple

from . import Device

RS = 0x01
EN = 0x04
BACKLIGHT = 0x08

#: Where each row starts in display memory. Rows 3 and 4 continue rows 1
#: and 2 on a 20-column display (0x14, 0x54); a 16x4 uses 0x10, 0x50.
ROW_STARTS = {16: (0x00, 0x40, 0x10, 0x50), 20: (0x00, 0x40, 0x14, 0x54)}
SIZES = {"16x2": (16, 2), "20x4": (20, 4)}

#: Long enough for the slowest step (the first wake-up needs 4.1 ms).
STEP_PAUSE = 0.005

#: Characters the display's standard (A00) font has somewhere else.
_SPECIAL = {"°": 0xDF, "→": 0x7E, "←": 0x7F}

#: One step: the bytes to write in one transfer, and what they mean.
Step = Tuple[bytes, str]


def _nibble(value: int, light: int) -> bytes:
    """Put four bits on D4–D7 and strobe E: high, then low."""
    return bytes([value | EN | light, value | light])


def _byte(value: int, light: int, rs: int = 0) -> bytes:
    return _nibble((value & 0xF0) | rs, light) + _nibble(((value << 4) & 0xF0) | rs, light)


def _display_control(on: bool, cursor: bool, blink: bool) -> int:
    return 0x08 | (0x04 if on else 0) | (0x02 if cursor else 0) | (0x01 if blink else 0)


def compose(message: str, size: str = "16x2", backlight: bool = True) -> List[Step]:
    """Turn a message into steps, starting from a full (re)initialisation.

    One instruction per line. Plain words are commands — ``clear``, ``home``,
    ``line 2``, ``backlight on/off``, ``cursor on/off``, ``blink on/off``,
    ``display on/off`` — and anything else is text. Each text line starts a
    new row unless a ``line N``, ``clear`` or ``home`` just placed the cursor.
    """
    cols, rows = SIZES[size]
    light = BACKLIGHT if backlight else 0
    steps: List[Step] = [
        (bytes([light]), "backlight " + ("on" if light else "off") + ", every other line low"),
        (_nibble(0x30, light), "wake-up 1 of 3"),
        (_nibble(0x30, light), "wake-up 2 of 3"),
        (_nibble(0x30, light), "wake-up 3 of 3"),
        (_nibble(0x20, light), "switch to 4-bit mode"),
        (_byte(0x28, light), "4-bit, 2 lines, 5x8 font"),
        (_byte(0x0C, light), "display on, cursor off"),
        (_byte(0x01, light), "clear"),
        (_byte(0x06, light), "text moves left to right"),
    ]
    display = {"on": True, "cursor": False, "blink": False}
    row, placed, written_any = 0, True, False

    def goto(r: int) -> None:
        nonlocal row, placed
        row, placed = r, True
        steps.append((_byte(0x80 | ROW_STARTS[cols][r], light), f"go to the start of line {r + 1}"))

    for raw in message.splitlines():
        line = raw.strip()
        word = line.lower()
        if not line:
            continue
        match = re.fullmatch(r"line\s*(\d+)", word)
        if match:
            wanted = int(match.group(1))
            if not 1 <= wanted <= rows:
                steps.append((b"", f"skipped '{line}': a {size} display has lines 1 to {rows}"))
                continue
            goto(wanted - 1)
        elif word == "clear":
            steps.append((_byte(0x01, light), "clear"))
            row, placed = 0, True
        elif word == "home":
            steps.append((_byte(0x02, light), "cursor to the top left"))
            row, placed = 0, True
        elif word in ("backlight on", "backlight off"):
            light = BACKLIGHT if word.endswith("on") else 0
            steps.append((bytes([light]), word))
        elif re.fullmatch(r"(cursor|blink|display) (on|off)", word):
            what, state = word.split()
            display[what] = state == "on"
            steps.append((_byte(_display_control(**display), light), word))
        else:
            if written_any and not placed:
                if row + 1 >= rows:
                    steps.append((b"", f"skipped '{line}': no line {row + 2} on a {size} display"))
                    continue
                goto(row + 1)
            if len(line) > cols:
                steps.append((b"", f"'{line}' is cut to {cols} characters"))
                line = line[:cols]
            for ch in line:
                code = _SPECIAL.get(ch, ord(ch))
                meaning = repr(ch)
                if not 0x20 <= code <= 0xFF or (code > 0x7F and ch not in _SPECIAL):
                    code, meaning = ord("?"), f"{ch!r} is not in the display's font, so '?'"
                steps.append((_byte(code, light, RS), meaning))
            written_any, placed = True, False
    return steps


def script(steps: List[Step]) -> str:
    """One step per line: the hex, then its meaning as a comment."""
    width = max((len(data.hex(" ")) for data, _ in steps), default=0)
    lines = []
    for data, meaning in steps:
        hex_part = data.hex(" ")
        lines.append(f"{hex_part:<{width}}  # {meaning}" if hex_part else f"# {meaning}")
    return "\n".join(lines)


def parse_script(text: str) -> List[bytes]:
    """The transfers in a script: comments and blank lines are ignored."""
    transfers = []
    for number, raw in enumerate(text.splitlines(), start=1):
        code = raw.split("#", 1)[0]
        cleaned = re.sub(r"0x|[\s,:]", "", code, flags=re.IGNORECASE)
        if not cleaned:
            continue
        if not re.fullmatch(r"[0-9a-fA-F]+", cleaned) or len(cleaned) % 2:
            raise ValueError(f"line {number} is not whole hex bytes: {raw.strip()!r}")
        transfers.append(bytes.fromhex(cleaned))
    return transfers


def send(i2c, address: int, transfers: List[bytes]) -> int:
    """Write each transfer on its own, pausing after each. Returns bytes sent."""
    for data in transfers:
        i2c.write(address, data)
        time.sleep(STEP_PAUSE)
    return sum(len(data) for data in transfers)


DEVICES = [
    Device(
        name="LCD (PCF8574 backpack)",
        bus="i2c",
        summary="HD44780 character display",
        addresses=(0x27, 0x3F),
        verified=True,  # 16x2 at 0x27 on a v4, 2026-09-29
    ),
]
