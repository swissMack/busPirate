"""Command line entry point: ``python -m buspirate`` or ``buspirate``."""

from __future__ import annotations

import argparse
import logging
import sys

from . import BusPirate, BusPirateError, discover, resolve
from .i2c import I2C
from .spi import SPI


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-p",
        "--port",
        default="auto",
        help="serial port, or 'auto' to detect it (the default)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log raw bytes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="buspirate",
        description="Talk to a Bus Pirate from the command line.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("ports", help="list serial ports and flag the likely one")
    listing.add_argument("--all", action="store_true", help="include unlikely ports")

    ping = sub.add_parser("ping", help="connect and report what the device is")
    _add_common(ping)

    scan = sub.add_parser("i2c-scan", help="list the I2C addresses that respond")
    _add_common(scan)
    scan.add_argument(
        "--speed",
        type=int,
        default=I2C.SPEED_100KHZ,
        choices=[0, 1, 2, 3],
        help="0=5kHz 1=50kHz 2=100kHz 3=400kHz (default: 2)",
    )
    scan.add_argument("--no-power", action="store_true", help="leave Vreg off")
    scan.add_argument("--no-pullups", action="store_true", help="leave pull-ups off")

    flash = sub.add_parser("spi-id", help="send 0x9F (JEDEC ID) and print the reply")
    _add_common(flash)
    flash.add_argument(
        "--speed",
        type=int,
        default=SPI.SPEED_1MHZ,
        choices=list(range(8)),
        help="0=30kHz .. 7=8MHz (default: 3, 1MHz)",
    )

    dash = sub.add_parser("dashboard", help="open the web dashboard in a browser")
    dash.add_argument("--host", default="127.0.0.1", help="loopback addresses only")
    dash.add_argument("--port-number", type=int, default=8765, dest="http_port")
    dash.add_argument(
        "--demo",
        action="store_true",
        help="run against a simulated Bus Pirate, with no hardware",
    )
    dash.add_argument(
        "--variant",
        default="v3",
        choices=["v3", "v4"],
        help="which device the demo simulates (default: v3)",
    )
    dash.add_argument("--no-browser", action="store_true", help="do not open a browser")
    return parser


def cmd_ports(args) -> int:
    candidates = discover(include_unlikely=args.all)
    if not candidates:
        hidden = len(discover(include_unlikely=True))
        if hidden and not args.all:
            print(
                f"No USB serial adapters found. ({hidden} other port(s) exist — "
                "Bluetooth and similar; pass --all to see them.)"
            )
        else:
            print("No serial ports found. Is the Bus Pirate plugged in?")
        return 1
    for candidate in candidates:
        mark = "*" if candidate.likely_bus_pirate else " "
        print(f" {mark} {candidate.describe()}")
    if any(c.likely_bus_pirate for c in candidates):
        print("\n* = looks like a Bus Pirate; --port auto will choose it.")
    else:
        print("\nNothing looks like a Bus Pirate. Pass --port explicitly.")
    return 0


def cmd_ping(args) -> int:
    with BusPirate(resolve(args.port)) as bp:
        print(f"{bp.port}: {bp.profile.describe()}")
        print(f"  bitbang protocol BBIO{bp.bitbang_version}")
        print(f"  features: {', '.join(sorted(bp.profile.capabilities)) or 'none'}")
    return 0


def cmd_i2c_scan(args) -> int:
    with BusPirate(resolve(args.port)) as bp:
        with bp.i2c() as i2c:
            i2c.configure_peripherals(
                power=not args.no_power, pullups=not args.no_pullups
            )
            i2c.set_speed(args.speed)
            found = i2c.scan()
    if not found:
        print("No devices responded. Check pull-ups, power, and SDA/SCL order.")
        return 1
    print(f"{len(found)} device(s):")
    for address in found:
        print(
            f"  0x{address:02X}  (write 0x{address << 1:02X} / "
            f"read 0x{(address << 1) | 1:02X})"
        )
    return 0


def cmd_spi_id(args) -> int:
    with BusPirate(resolve(args.port)) as bp:
        with bp.spi() as spi:
            spi.configure_peripherals(power=True)
            spi.set_speed(args.speed)
            spi.set_mode(0)
            jedec = spi.write_then_read(b"\x9f", 3)
    print(f"JEDEC ID: {jedec.hex(' ')}")
    if jedec in (b"\x00\x00\x00", b"\xff\xff\xff"):
        print("(all-zero or all-one reply usually means MISO is not connected)")
        return 1
    return 0


def cmd_dashboard(args) -> int:
    from .web.server import serve

    where = f"http://{args.host}:{args.http_port}/"
    print(f"Dashboard on {where}" + ("  (simulated device)" if args.demo else ""))
    print("Press Ctrl-C to stop.")
    try:
        serve(
            host=args.host,
            port=args.http_port,
            use_fake=args.demo or None,
            fake_variant=args.variant,
            open_browser=not args.no_browser,
        )
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING,
        format="%(message)s",
    )
    handlers = {
        "ports": cmd_ports,
        "ping": cmd_ping,
        "i2c-scan": cmd_i2c_scan,
        "spi-id": cmd_spi_id,
        "dashboard": cmd_dashboard,
    }
    try:
        return handlers[args.command](args)
    except BusPirateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
