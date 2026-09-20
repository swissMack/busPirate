"""Command line entry point: ``python -m buspirate``."""

from __future__ import annotations

import argparse
import logging
import sys

from . import BusPirate, BusPirateError
from .i2c import I2C
from .spi import SPI


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--port", required=True, help="serial port")
    parser.add_argument("-v", "--verbose", action="store_true", help="log raw bytes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="buspirate", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ping = sub.add_parser("ping", help="enter binary mode and report success")
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

    sniff = sub.add_parser("spi-id", help="send 0x9F (JEDEC ID) and print the reply")
    _add_common(sniff)
    sniff.add_argument(
        "--speed",
        type=int,
        default=SPI.SPEED_1MHZ,
        choices=list(range(8)),
        help="0=30kHz .. 7=8MHz (default: 3, 1MHz)",
    )
    return parser


def cmd_ping(args) -> int:
    with BusPirate(args.port):
        print(f"{args.port}: binary mode OK")
    return 0


def cmd_i2c_scan(args) -> int:
    with BusPirate(args.port) as bp:
        with bp.i2c() as i2c:
            i2c.configure_peripherals(
                power=not args.no_power, pullups=not args.no_pullups
            )
            i2c.set_speed(args.speed)
            found = i2c.scan()
    if not found:
        print("no devices responded — check power, pull-ups and wiring")
        return 1
    print(f"{len(found)} device(s):")
    for address in found:
        print(f"  0x{address:02X}  (write 0x{address << 1:02X} / read 0x{(address << 1) | 1:02X})")
    return 0


def cmd_spi_id(args) -> int:
    with BusPirate(args.port) as bp:
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


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )
    handlers = {
        "ping": cmd_ping,
        "i2c-scan": cmd_i2c_scan,
        "spi-id": cmd_spi_id,
    }
    try:
        return handlers[args.command](args)
    except BusPirateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
