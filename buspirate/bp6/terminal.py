"""The Bus Pirate 6's text terminal, used only to switch BPIO2 on.

What the real board does (2026-10-14, firmware built 2026-10-12): only "\\r"
is Enter; the first key after boot gets "VT100 compatible color mode? (Y/n)>",
which takes its answer only as "n\\r" in one write; ``binmode`` lists the
binary modes, "2" picks BPIO2 and "n" declines to save it, so nothing on the
board changes beyond this boot.
"""

from __future__ import annotations

import time

from ..exceptions import ModeError

COLOR_PROMPT = "VT100 compatible color mode?"


def _read_until(serial, notify, marks, timeout: float) -> str:
    seen = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = serial.read(256)
        if chunk:
            seen += chunk
            notify("rx", bytes(chunk))
            text = seen.decode("utf-8", "replace")
            if any(mark in text for mark in marks):
                return text
        else:
            time.sleep(0.01)
    return seen.decode("utf-8", "replace")


def _send(serial, notify, keys: bytes) -> None:
    serial.write(keys)
    notify("tx", keys)


def select_bpio2(serial, notify, timeout: float = 3.0) -> None:
    _send(serial, notify, b"\x03")
    text = _read_until(serial, notify, ("> ", COLOR_PROMPT), timeout)
    if COLOR_PROMPT in text:
        _send(serial, notify, b"n\r")
        _read_until(serial, notify, ("> ",), timeout)
    _send(serial, notify, b"binmode\r")
    text = _read_until(serial, notify, ("x to exit",), timeout)
    if "BPIO2" not in text:
        raise ModeError(
            "this Bus Pirate's firmware has no BPIO2 binary mode. Update it: type "
            "$ in its terminal, then copy bus_pirate6.uf2 onto the RP2350 disk "
            "(see the Bus Pirate 6 guide). It said: " + text.strip()[-160:]
        )
    _send(serial, notify, b"2\r")
    _read_until(serial, notify, ("y/n",), timeout)
    _send(serial, notify, b"n\r")
    _read_until(serial, notify, ("> ",), timeout)
