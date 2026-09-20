"""UART: watch a serial line, or talk to one."""

from __future__ import annotations

from ...uart import UART
from ..registry import Action, Panel, Param, Wire, hexdump, text
from ..wiring import CABLE_CAVEAT, POWER_NOTE, colour

BAUD_CHOICES = [
    {"value": UART.BAUD_300, "label": "300"},
    {"value": UART.BAUD_1200, "label": "1200"},
    {"value": UART.BAUD_2400, "label": "2400"},
    {"value": UART.BAUD_4800, "label": "4800"},
    {"value": UART.BAUD_9600, "label": "9600"},
    {"value": UART.BAUD_19200, "label": "19200"},
    {"value": UART.BAUD_31250, "label": "31250 (MIDI)"},
    {"value": UART.BAUD_38400, "label": "38400"},
    {"value": UART.BAUD_57600, "label": "57600"},
    {"value": UART.BAUD_115200, "label": "115200"},
]

FRAMING_CHOICES = [
    {"value": 0, "label": "8 data bits, no parity (usual)"},
    {"value": 1, "label": "8 data bits, even parity"},
    {"value": 2, "label": "8 data bits, odd parity"},
    {"value": 3, "label": "9 data bits, no parity"},
]


def _configure(ctx, baud, framing, stop_bits, power):
    ctx.mode.configure_peripherals(power=power)
    ctx.mode.set_baudrate(baud)
    ctx.mode.configure(databits_parity=framing, stop_bits=stop_bits)
    label = dict((c["value"], c["label"]) for c in BAUD_CHOICES)[baud]
    return text(f"UART set to {label} baud.", tone="good")


def _send_text(ctx, message, newline):
    payload = message.encode("utf-8", "replace")
    if newline:
        payload += b"\r\n"
    ctx.mode.write(payload)
    return text(f"Sent {len(payload)} byte(s).", tone="good")


def _send_bytes(ctx, data):
    ctx.mode.write(data)
    return text(f"Sent {len(data)} byte(s).", tone="good")


def _listen(ctx, enable):
    if enable:
        ctx.mode.start_receive()
        return text(
            "Listening. Received bytes appear below — press Read to collect them.",
            tone="good",
        )
    ctx.mode.stop_receive()
    return text("Stopped listening.")


def _read(ctx, max_bytes):
    data = ctx.mode.read_available(max_bytes)
    if not data:
        return text(
            "Nothing received yet. If you expected traffic, check that MISO is "
            "on the target's TX pin and that the baud rate matches."
        )
    printable = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return hexdump(data, caption=f"{len(data)} byte(s) received — {printable}")


PANEL = Panel(
    id="uart",
    title="UART",
    blurb="Listen to a serial line, or send it something.",
    mode="uart",
    order=40,
    wiring=[
        Wire("MISO", colour("MISO"), "TX", "the target's transmit pin"),
        Wire("MOSI", colour("MOSI"), "RX", "the target's receive pin"),
        Wire("GND", colour("GND"), "GND", "always connect this first"),
        Wire("+3.3V", colour("+3.3V"), "VCC", "only if powering the target"),
    ],
    notes=[
        "TX and RX cross over: the Bus Pirate's MISO listens to the target's "
        "TX. If you see nothing, swapping these two is the first thing to try.",
        "Garbled characters mean the baud rate is wrong, not the wiring.",
        POWER_NOTE,
        CABLE_CAVEAT,
    ],
    actions=[
        Action(
            name="configure",
            label="Set the line up",
            primary=True,
            recipe=True,
            params=[
                Param("baud", "enum", "Baud rate", default=UART.BAUD_115200, choices=BAUD_CHOICES),
                Param("framing", "enum", "Data bits and parity", default=0, choices=FRAMING_CHOICES),
                Param(
                    "stop_bits",
                    "enum",
                    "Stop bits",
                    default=1,
                    choices=[{"value": 1, "label": "1"}, {"value": 2, "label": "2"}],
                ),
                Param("power", "bool", "Power the target (3.3V + 5V)", default=False),
            ],
            handler=_configure,
        ),
        Action(
            name="listen",
            label="Start or stop listening",
            help="While listening, the Bus Pirate forwards everything it hears.",
            params=[Param("enable", "bool", "Listening", default=True)],
            handler=_listen,
        ),
        Action(
            name="read",
            label="Read what arrived",
            params=[Param("max_bytes", "int", "Up to", default=256, minimum=1, maximum=4096)],
            handler=_read,
        ),
        Action(
            name="send_text",
            label="Send text",
            params=[
                Param("message", "text", "Text", default="AT", placeholder="AT"),
                Param("newline", "bool", "Append CR LF", default=True),
            ],
            handler=_send_text,
        ),
        Action(
            name="send_bytes",
            label="Send raw bytes",
            params=[Param("data", "bytes", "Bytes", default="41 54 0d 0a")],
            handler=_send_bytes,
        ),
    ],
)
