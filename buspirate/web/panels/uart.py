"""UART: watch a serial line, or talk to one."""

from __future__ import annotations

import time

from ... import device as device_module
from ...uart import UART
from ..registry import Action, Panel, Param, Wire, hexdump, live, text
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
    _listen_if_needed(ctx)
    label = dict((c["value"], c["label"]) for c in BAUD_CHOICES)[baud]
    return text(f"UART set to {label} baud, and listening: what comes back after "
                "you send shows up under Send.", tone="good")


def _send_text(ctx, message, newline):
    payload = message.encode("utf-8", "replace")
    if newline:
        payload += b"\r\n"
    return _send(ctx, payload)


def _send_bytes(ctx, data):
    return _send(ctx, data)


#: How long to wait for a reply before showing what came back.
REPLY_WAIT = 0.3


def _send(ctx, payload):
    """Send, then show what came back, so nobody has to know to press Read.

    Without a setup the transmit pin is not driving: the firmware would
    acknowledge every byte while nothing reached the wire, so set it up.
    """
    note = _set_up_if_needed(ctx)
    _listen_if_needed(ctx)
    ctx.mode.write(payload)
    sent = f"{note}Sent {len(payload)} byte(s)."
    if getattr(ctx.mode, "listening", None) is None:
        # A board with no buffered receive (the Bit Pirate): nothing to show.
        return text(sent, tone="good")
    time.sleep(REPLY_WAIT)
    reply = ctx.mode.read_available(4096)
    if not reply:
        return text(sent + f" Nothing came back within {REPLY_WAIT:.1f} s; "
                    "Check for more replies collects anything slower.", tone="good")
    return hexdump(reply, caption=f"{sent} Received back {len(reply)} byte(s): "
                                  f"{_printable(reply)}")


def _printable(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def _listen_if_needed(ctx) -> None:
    """Always listen in UART mode: there is no reason not to, and replies
    only reach the dashboard while the firmware forwards them."""
    if getattr(ctx.mode, "listening", True) is False:
        ctx.mode.start_receive()


def _set_up_if_needed(ctx) -> str:
    """Listening before Set the line up leaves the firmware at 300 baud with
    its transmit pin not driving: a loop or an unconnected RX then floats,
    and the noise is forwarded as bytes. Set the defaults first."""
    # Boards whose UART class has no such state (the Bit Pirate sets its
    # line up through its own commands) have nothing to fix here.
    if getattr(ctx.mode, "configured", True):
        return ""
    ctx.mode.set_baudrate(UART.BAUD_115200)
    ctx.mode.configure()
    return ("The line was not set up yet, so it is now 115200 baud, 8 data "
            "bits, no parity, 1 stop bit, driven. ")


def _read(ctx, max_bytes):
    _set_up_if_needed(ctx)
    _listen_if_needed(ctx)
    data = ctx.mode.read_available(max_bytes)
    if not data:
        return text(
            "Nothing more has arrived. If you expected a reply, check that MISO "
            "is on the target's TX pin and that the baud rate matches."
        )
    return hexdump(data, caption=f"{len(data)} byte(s) received — {_printable(data)}")


def _monitor(ctx):
    _set_up_if_needed(ctx)
    ctx.mode.start_receive()  # again, harmlessly: the stream reads from here on
    return live(
        "UART monitor",
        decoder="text",
        caption="Everything arriving on the line, as it arrives.",
    )


def _bridge(ctx):
    ctx.mode.start_bridge()
    return live(
        "UART bridge",
        decoder="text",
        caption="The Bus Pirate is now a plain USB-to-serial adapter.",
        warning="There is no way out of bridge mode in software — the "
        "firmware needs a power cycle. Unplug the Bus Pirate and plug it back "
        "in, then reconnect.",
    )


PANEL = Panel(
    id="uart",
    refcard_column='UART',
    refcard_rows=['GND'],
    doc="uart",
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
                Param("power", "bool", "Power the target (3.3V + 5V)", default=False,
                      requires=device_module.CAP_SUPPLIES),
            ],
            handler=_configure,
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
        Action(
            name="read",
            requires=device_module.CAP_UART_BUFFERED,
            label="Check for more replies",
            help="Send already shows what comes back within a moment. This "
            "collects anything slower, or anything the device sent on its own.",
            params=[Param("max_bytes", "int", "Up to", default=256, minimum=1, maximum=4096)],
            handler=_read,
        ),
        Action(
            name="monitor",
            label="Watch the line",
            recipe=True,
            stream=True,
            help="A live view, for a device that talks on its own — boot "
            "messages, a GPS. While it runs nothing can be sent: press Stop "
            "first.",
            handler=_monitor,
        ),
        Action(
            name="bridge",
            requires=device_module.CAP_UART_BRIDGE,
            label="Transparent bridge",
            stream=True,
            confirm="Bridge mode cannot be stopped from software — you will "
            "have to unplug the Bus Pirate to get it back. Continue?",
            help="Turns the Bus Pirate into a plain USB-to-serial adapter. "
            "Only a power cycle ends it.",
            handler=_bridge,
        ),
    ],
)
