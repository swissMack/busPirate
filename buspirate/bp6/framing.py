"""COBS framing for BPIO2.

Every request and every response is one FlatBuffer, COBS-encoded so it holds
no zero bytes, and ended by a single ``0x00`` (firmware src/binmode/bpio.c,
nanocobs). There is no length prefix.
"""

from __future__ import annotations

from typing import List

DELIMITER = b"\x00"


def cobs_encode(data: bytes) -> bytes:
    out = bytearray()
    block = bytearray()
    for byte in bytes(data):
        if byte == 0:
            out.append(len(block) + 1)
            out += block
            block.clear()
        else:
            block.append(byte)
            if len(block) == 254:
                out.append(0xFF)
                out += block
                block.clear()
    out.append(len(block) + 1)
    out += block
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    data = bytes(data)
    out = bytearray()
    index = 0
    while index < len(data):
        code = data[index]
        if code == 0:
            raise ValueError("a zero byte inside a COBS frame")
        index += 1
        end = index + code - 1
        if end > len(data):
            raise ValueError("a COBS frame ends early")
        chunk = data[index:end]
        if 0 in chunk:
            raise ValueError("a zero byte inside a COBS frame")
        out += chunk
        index = end
        if code < 0xFF and index < len(data):
            out.append(0)
    return bytes(out)


def frame(payload: bytes) -> bytes:
    """``payload`` ready for the wire: encoded, then the delimiter."""
    return cobs_encode(payload) + DELIMITER


class FrameReader:
    """Collects bytes off the port and hands back whole frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> List[bytes]:
        """Every frame completed by ``data``, delimiter included."""
        self._buffer += data
        frames = []
        while True:
            end = self._buffer.find(0)
            if end < 0:
                return frames
            raw = bytes(self._buffer[: end + 1])
            del self._buffer[: end + 1]
            if len(raw) > 1:
                frames.append(raw)
