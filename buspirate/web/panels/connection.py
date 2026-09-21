"""Connect, identify, and check the device is healthy."""

from __future__ import annotations

from ... import device as device_module
from ...exceptions import BusPirateError
from ..registry import Action, Panel, Param, keyvalue, table, text
from ..wiring import BOARDS, SEEED_CABLE


def _connect(ctx, port):
    status = ctx.session.connect_blocking(port or None)
    return text(
        f"Connected to {status['port']} — {status['description']}.", tone="good"
    )


def _disconnect(ctx):
    ctx.session.disconnect_blocking()
    return text("Disconnected. The Bus Pirate is back in its terminal.")


def _identify(ctx):
    profile = ctx.bp.profile
    return keyvalue(
        [
            ["Hardware", profile.describe()],
            ["Firmware", profile.firmware or "not reported"],
            ["Bootloader", profile.bootloader or "not reported"],
            ["Device ID", profile.devid or "not reported"],
            ["Bitbang protocol", f"BBIO{ctx.bp.bitbang_version}"],
            ["Features", ", ".join(sorted(profile.capabilities)) or "none detected"],
        ],
        caption="Read from the firmware's 'i' command at connect time",
    )


def _legend(ctx):
    rows = [
        [index, signal, name, hexcode]
        for index, (signal, hexcode, name) in enumerate(SEEED_CABLE, start=1)
    ]
    return table(
        ["Pin", "Signal", "Cable colour", "Hex"],
        rows,
        caption=(
            "Seeed/Adafruit probe cable, pin 1 first. Pin 1 is MISO (black) "
            "and pin 10 is GND (brown). Hold your cable against this before "
            "wiring anything — a reversed cable is the commonest mistake."
        ),
    )


def _set_variant(ctx, variant):
    if variant == "auto":
        ctx.session.display_variant = None
        return text(
            "Following the connected board again.", tone="good"
        )
    if variant not in BOARDS:
        raise BusPirateError(
            f"{variant!r} is not a board this dashboard knows — "
            f"pick one of: auto, {', '.join(sorted(BOARDS))}"
        )
    ctx.session.display_variant = variant
    return text(f"Showing {BOARDS[variant]['label']}.", tone="good")


def _self_test(ctx):
    errors = ctx.bp.self_test()
    if errors:
        return text(
            f"Self-test reported {errors} error(s). Disconnect everything from "
            "the probe and run it again before believing it.",
            tone="warn",
        )
    return text("Self-test passed with no errors.", tone="good")


PANEL = Panel(
    id="connection",
    doc="macos-setup",
    title="Connection",
    blurb="Find the Bus Pirate, connect to it, and confirm what it is.",
    mode=None,
    order=10,
    notes=[
        "On macOS always use the /dev/cu.* device. The matching /dev/tty.* "
        "device is the same hardware but blocks on carrier detect, which looks "
        "exactly like a hang.",
    ],
    actions=[
        Action(
            name="connect",
            label="Connect",
            primary=True,
            help="Leave the port blank to pick the most likely one automatically.",
            params=[
                Param(
                    "port",
                    "text",
                    "Port",
                    default="",
                    placeholder="auto",
                    help="A /dev path, or blank for automatic.",
                )
            ],
            handler=_connect,
            allow_while_streaming=True,
        ),
        Action(
            name="disconnect",
            label="Disconnect",
            handler=_disconnect,
            allow_while_streaming=True,
            help="Stops anything that is running, resets the Bus Pirate to "
            "its terminal, and releases the port.",
        ),
        Action(
            name="identify",
            label="What is this device?",
            help="Everything the firmware told us about itself.",
            handler=_identify,
        ),
        Action(
            name="set_variant",
            label="Show a different board",
            help="The dashboard follows whatever is plugged in. Override this "
            "to read about the other version — the header pinout and the LED "
            "behaviour both differ.",
            params=[
                Param(
                    "variant",
                    "enum",
                    "Board to show",
                    default="auto",
                    choices=[
                        {"value": "auto", "label": "Follow the connected board"},
                        {"value": "v3", "label": "Bus Pirate v3"},
                        {"value": "v4", "label": "Bus Pirate v4"},
                    ],
                ),
            ],
            handler=_set_variant,
        ),
        Action(
            name="legend",
            label="Show the cable legend",
            help="Which probe wire is which signal.",
            handler=_legend,
        ),
        Action(
            name="self_test",
            label="Run self-test",
            help="Bus Pirate v3 only. Unplug the probe from any target first.",
            requires=device_module.CAP_SELF_TEST,
            confirm="Disconnect the probe cable from your target before running "
            "the self-test. Continue?",
            handler=_self_test,
        ),
    ],
)
