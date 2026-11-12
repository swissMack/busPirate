"""Smart card (ISO 7816-3) answer to reset: what the bytes a card sends after reset say."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

DEVICES: list = []

_CONVENTIONS = {0x3B: "direct", 0x3F: "inverse"}


def parse_atr(data: bytes) -> Dict[str, Any]:
    """Decode an ATR: TS, T0, the interface bytes, the historical bytes and TCK.

    ``protocols`` lists the transmission protocols the TDi bytes announce (T=0
    when there is no TD1); T=15 marks global interface bytes, not a protocol,
    and is left out. As ISO 7816-3 says, a TCK is expected whenever any TDi
    announces a T other than 0, T=15 included. ``tck_ok`` is True or False
    when the TCK is checked, and None when none is expected or it is missing.
    ``complete`` is False when fewer bytes arrived than T0 and the TDi announce
    (a missing TCK included).
    Raises ValueError on empty data or a TS that is neither 0x3B nor 0x3F.
    """
    data = bytes(data)
    if not data:
        raise ValueError("the ATR is empty")
    if data[0] not in _CONVENTIONS:
        hint = (": 0x03 is an inverse-convention card (0x3F) read as direct"
                if data[0] == 0x03 else "")
        raise ValueError("TS must be 0x3B (direct) or 0x3F (inverse), not 0x%02X%s"
                         % (data[0], hint))
    complete = True
    protocols = set()  # type: set
    ta1 = None  # type: Optional[int]
    ta2 = None  # type: Optional[int]
    historical = b""
    tck_ok = None  # type: Optional[bool]
    tck_expected = False
    pos = 1
    if len(data) < 2:
        complete = False
    else:
        t0 = data[1]
        k = t0 & 0x0F
        y = t0 >> 4
        pos = 2
        level = 1
        while y and complete:
            td = None
            for bit in (1, 2, 4, 8):  # TAi, TBi, TCi, TDi
                if not y & bit:
                    continue
                if pos >= len(data):
                    complete = False
                    break
                if bit == 1 and level == 1:
                    ta1 = data[pos]
                if bit == 1 and level == 2:
                    ta2 = data[pos]  # present: the card is in specific mode
                if bit == 8:
                    td = data[pos]
                pos += 1
            if td is None or not complete:
                break
            if td & 0x0F:
                tck_expected = True
            if td & 0x0F != 0x0F:
                protocols.add(td & 0x0F)
            y = td >> 4
            level += 1
        if complete:
            historical = data[pos:pos + k]
            if len(historical) < k:
                complete = False
            pos += len(historical)
        if complete and tck_expected:
            if pos < len(data):
                check = 0
                for byte in data[1:pos + 1]:
                    check ^= byte
                tck_ok = check == 0
            else:
                complete = False
    if not protocols:
        protocols.add(0)
    text = historical.decode("ascii") if historical and all(
        0x20 <= b <= 0x7E for b in historical) else ""
    found = sorted(protocols)  # type: List[int]
    return {"convention": _CONVENTIONS[data[0]], "protocols": found,
            "historical": historical.hex().upper(), "historical_text": text,
            "ta1": ta1, "ta2": ta2, "tck_ok": tck_ok, "complete": complete}
