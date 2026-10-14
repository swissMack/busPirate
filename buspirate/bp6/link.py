"""One BPIO2 request, one reply, over the board's binary port.

In UART mode the firmware also sends unsolicited DataResponses with
``is_async`` set, whenever the target transmits. They can arrive before the
reply to whatever was asked, so they are set aside in ``async_rx`` rather
than mistaken for it.

A reply can also arrive late — to a request that already timed out, say on a
board that was just plugged back in. So bytes already waiting are cleared
before each request (their async data kept), and a reply of the wrong kind
for the request is skipped. Either way, one late answer never shifts every
later reply by one.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable, Deque, Optional

from ..exceptions import ProtocolError
from .bpio import RequestPacket as _RP
from .bpio.RequestPacketContents import RequestPacketContents
from .framing import FrameReader, cobs_decode, frame
from .protocol import Response, parse_response

#: What kind of reply each kind of request gets.
_REPLY_KIND = {
    RequestPacketContents.StatusRequest: "status",
    RequestPacketContents.ConfigurationRequest: "configuration",
    RequestPacketContents.DataRequest: "data",
}


def _expected(payload: bytes) -> Optional[str]:
    try:
        return _REPLY_KIND.get(_RP.RequestPacket.GetRootAs(payload, 0).ContentsType())
    except Exception:  # noqa: BLE001 - a request we built ourselves; be lenient
        return None


class BpioLink:
    def __init__(self, serial, notify: Callable[[str, bytes], None], timeout: float = 1.0) -> None:
        self.serial = serial
        self._notify = notify
        self.timeout = timeout
        self._reader = FrameReader()
        self._frames: Deque[bytes] = deque()
        self.async_rx = bytearray()

    def request(self, payload: bytes, timeout: Optional[float] = None,
                quiet: bool = False) -> Response:
        """Send ``payload`` and return its reply.

        ``quiet`` keeps the exchange out of the traffic hooks — for the
        dashboard's background status poll, which would otherwise fill the
        traffic log with two lines a second.
        """
        self._clear_stale(quiet)
        expected = _expected(payload)
        raw = frame(payload)
        self.serial.write(raw)
        flush = getattr(self.serial, "flush", None)
        if flush is not None:
            flush()
        if not quiet:
            self._notify("tx", raw)
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            response = self._next(deadline, quiet)
            if response is None:
                raise ProtocolError(
                    "the Bus Pirate 6 did not answer on its BPIO2 port. Is BPIO2 "
                    "selected (binmode, option 2)?"
                )
            if response.is_async:
                self.async_rx += response.data
                continue
            if expected and response.kind not in (expected, "error"):
                continue  # a late answer to an earlier request
            return response

    def poll_async(self, seconds: float) -> bytes:
        """Gather async data for up to ``seconds``; return it and clear it."""
        deadline = time.monotonic() + seconds
        while True:
            response = self._next(deadline)
            if response is None:
                break
            if response.is_async:
                self.async_rx += response.data
        data = bytes(self.async_rx)
        self.async_rx.clear()
        return data

    def _clear_stale(self, quiet: bool) -> None:
        """Drop replies nobody is waiting for; keep what the target sent."""
        waiting = getattr(self.serial, "in_waiting", 0) or 0
        while waiting:
            chunk = self.serial.read(waiting)
            if not chunk:
                break
            for raw in self._reader.feed(chunk):
                if not quiet:
                    self._notify("rx", raw)
                self._frames.append(raw)
            waiting = getattr(self.serial, "in_waiting", 0) or 0
        while self._frames:
            response = self._parse(self._frames.popleft())
            if response is not None and response.is_async:
                self.async_rx += response.data

    @staticmethod
    def _parse(raw: bytes) -> Optional[Response]:
        """A frame's reply, or None for a frame too damaged to read."""
        try:
            return parse_response(cobs_decode(raw[:-1]))
        except (ValueError, ProtocolError):
            return None

    def _next(self, deadline: float, quiet: bool = False) -> Optional[Response]:
        while True:
            while self._frames:
                response = self._parse(self._frames.popleft())
                if response is not None:
                    return response
            if time.monotonic() >= deadline:
                return None
            chunk = self.serial.read(256)
            if not chunk:
                time.sleep(0.002)
                continue
            for raw in self._reader.feed(chunk):
                if not quiet:
                    self._notify("rx", raw)
                self._frames.append(raw)
