"""One BPIO2 request, one reply, over the board's binary port.

In UART mode the firmware also sends unsolicited DataResponses with
``is_async`` set, whenever the target transmits. They can arrive before the
reply to whatever was asked, so they are set aside in ``async_rx`` rather
than mistaken for it.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable, Deque, Optional

from ..exceptions import ProtocolError
from .framing import FrameReader, cobs_decode, frame
from .protocol import Response, parse_response


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

    def _next(self, deadline: float, quiet: bool = False) -> Optional[Response]:
        while True:
            if self._frames:
                return parse_response(cobs_decode(self._frames.popleft()[:-1]))
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
