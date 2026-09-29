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
    label = dict((c["value"], c["label"]) for c in BAUD_CHOICES)[baud]
    return text(f"UART set to {label} baud.", tone="good")


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
    ctx.mode.write(payload)
    sent = f"{note}Sent {len(payload)} byte(s)."
    if not getattr(ctx.mode, "listening", False):
        return text(sent + " Not listening, so replies are not collected: "
                    "start listening to see them.", tone="good")
    time.sleep(REPLY_WAIT)
    reply = ctx.mode.read_available(4096)
    if not reply:
        return text(sent + f" Nothing came back within {REPLY_WAIT:.1f} s; "
                    "Read what arrived collects anything slower.", tone="good")
    return hexdump(reply, caption=f"{sent} Received back {len(reply)} byte(s): "
                                  f"{_printable(reply)}")


def _printable(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


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


def _listen(ctx, enable):
    if enable:
        note = _set_up_if_needed(ctx)
        ctx.mode.start_receive()
        return text(
            note + "Listening. Received bytes appear below — press Read to collect them.",
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
    return hexdump(data, caption=f"{len(data)} byte(s) received — {_printable(data)}")


def _monitor(ctx):
    _set_up_if_needed(ctx)
    ctx.mode.start_receive()
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
            name="listen",
            requires=device_module.CAP_UART_BUFFERED,
            label="Start or stop listening",
            help="While listening, the Bus Pirate forwards everything it hears.",
            params=[Param("enable", "bool", "Listening", default=True)],
            handler=_listen,
        ),
        Action(
            name="read",
            requires=device_module.CAP_UART_BUFFERED,
            label="Read what arrived",
            params=[Param("max_bytes", "int", "Up to", default=256, minimum=1, maximum=4096)],
            handler=_read,
        ),
        Action(
            name="monitor",
            label="Watch the line",
            recipe=True,
            stream=True,
            help="Live view of everything received. Better than Read for "
            "watching boot messages go by.",
            handler=_monitor,
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
