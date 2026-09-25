"""Turning a sniffer's byte stream into something readable.

The firmware's sniffers emit a compact escaped encoding rather than plain
bytes, and a read can land anywhere in it — mid-escape, mid-pair. Each decoder
is therefore a small state machine you feed as the bytes arrive.
"""

from __future__ import annotations

from typing import Dict, List


def _printable(value: int) -> str:
    return chr(value) if 32 <= value < 127 else "."


class Decoder:
    """Feed it bytes, get back a list of events for the live pane."""

    #: Shown above the stream so you know how to read it.
    legend = ""

    def feed(self, data: bytes) -> List[Dict]:  # pragma: no cover - interface
        raise NotImplementedError

    def flush(self) -> List[Dict]:
        return []


class I2CSnifferDecoder(Decoder):
    """``[`` start, ``]`` stop, ``\\`` escapes a data byte, ``+``/``-`` ACK/NACK."""

    legend = "[ start   ] stop   +ACK   -NACK   values are the bytes on the bus"

    def __init__(self) -> None:
        self._escaped = False

    def feed(self, data: bytes) -> List[Dict]:
        events = []
        for byte in data:
            if self._escaped:
                self._escaped = False
                events.append({"kind": "data", "text": f"{byte:02x}", "value": byte})
                continue
            char = chr(byte) if byte < 128 else ""
            if char == "\\":
                self._escaped = True
            elif char == "[":
                events.append({"kind": "start", "text": "START"})
            elif char == "]":
                events.append({"kind": "stop", "text": "STOP"})
            elif char == "+":
                events.append({"kind": "ack", "text": "+"})
            elif char == "-":
                events.append({"kind": "nack", "text": "-"})
            # Anything else is framing noise and is dropped deliberately.
        return events


class SPISnifferDecoder(Decoder):
    """``[``/``]`` chip select, ``\\`` escapes a MOSI byte then a MISO byte."""

    legend = "[ CS low   ] CS high   pairs are MOSI/MISO (firmware v5.1 and later)"

    def __init__(self) -> None:
        self._pending = []  # bytes collected since the escape character
        self._escaped = False

    def feed(self, data: bytes) -> List[Dict]:
        events = []
        for byte in data:
            if self._escaped:
                self._pending.append(byte)
                if len(self._pending) == 2:
                    mosi, miso = self._pending
                    self._pending = []
                    self._escaped = False
                    events.append(
                        {
                            "kind": "data",
                            "text": f"{mosi:02x}/{miso:02x}",
                            "mosi": mosi,
                            "miso": miso,
                        }
                    )
                continue
            char = chr(byte) if byte < 128 else ""
            if char == "\\":
                self._escaped = True
                self._pending = []
            elif char == "[":
                events.append({"kind": "start", "text": "CS↓"})
            elif char == "]":
                events.append({"kind": "stop", "text": "CS↑"})
        return events


class TextDecoder(Decoder):
    """Raw bytes, shown as hex with an ASCII gloss. Used for the UART echo."""

    legend = "Bytes received on the line, hex with printable characters alongside"

    def feed(self, data: bytes) -> List[Dict]:
        if not data:
            return []
        return [
            {
                "kind": "data",
                "text": data.hex(" "),
                "ascii": "".join(_printable(b) for b in data),
            }
        ]


class ConsoleDecoder(Decoder):
    """The board's own terminal, as the text a serial terminal would show.

    The firmware ends lines with CR LF. Dropping every CR, rather than
    translating the pair, means a CR and its LF split across two reads still
    come out as one newline. Tabs are kept — the v3 pin table is laid out with
    them — and so is backspace, which the firmware echoes as BS, space, BS
    and the pane applies. Any other non-printable byte becomes U+FFFD, so a
    garbled line looks garbled instead of silently losing characters.
    """

    legend = "The board's replies, as its own terminal prints them"

    def feed(self, data: bytes) -> List[Dict]:
        text = "".join(
            chr(b) if 32 <= b < 127 or b in (0x08, 0x09, 0x0A) else "\N{REPLACEMENT CHARACTER}"
            for b in data
            if b != 0x0D
        )
        return [{"kind": "console", "text": text}] if text else []


class VoltageDecoder(Decoder):
    """Continuous ADC readings: two bytes per sample, most significant first."""

    legend = "Voltage on the ADC probe, sampled continuously"

    FULL_SCALE = 6.6
    COUNTS = 1024.0

    def __init__(self) -> None:
        self._half = b""

    def feed(self, data: bytes) -> List[Dict]:
        buffer = self._half + data
        events = []
        count = len(buffer) // 2
        for index in range(count):
            raw = int.from_bytes(buffer[index * 2 : index * 2 + 2], "big")
            volts = raw * self.FULL_SCALE / self.COUNTS
            events.append({"kind": "value", "text": f"{volts:.2f} V", "volts": volts})
        self._half = buffer[count * 2 :]
        return events


DECODERS = {
    "console": ConsoleDecoder,
    "i2c-sniffer": I2CSnifferDecoder,
    "spi-sniffer": SPISnifferDecoder,
    "text": TextDecoder,
    "voltage": VoltageDecoder,
}


def make_decoder(name: str) -> Decoder:
    try:
        return DECODERS[name]()
    except KeyError:
        raise ValueError(f"no decoder called {name!r}") from None
