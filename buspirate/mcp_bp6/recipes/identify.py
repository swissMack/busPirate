"""``identify``: try the I2C, 1-Wire and SPI buses in turn and say what answered."""

from __future__ import annotations

from typing import Any, Dict

from ...exceptions import BusPirateError
from ...spiflash import SPIFlash
from . import Recipe, onewire, register, spi
from .i2c import _found, _open as _open_i2c

DOCS = "https://docs.buspirate.com/docs/"
WIRING = (("SDA / 1-Wire DQ", "IO0"), ("SCL", "IO1"), ("SPI MISO", "IO4"), ("SPI CS", "IO5"),
          ("SPI CLK", "IO6"), ("SPI MOSI", "IO7"), ("GND", "GND"), ("VCC", "VOUT"))
NEXT = ("nothing answered on I2C, 1-Wire or SPI. Check the target is powered and its ground "
        "is joined to GND; for I2C or 1-Wire, SDA/DQ on IO0 (and SCL on IO1) with pull-ups "
        "on; for SPI, CLK on IO6, MOSI on IO7, MISO on IO4 and CS on IO5 with WP/HOLD tied "
        "high. For a serial console use uart-console, with BP6 TX (IO4) to the target's RX.")


def _try(fn: Any) -> Dict[str, Any]:
    try:
        return fn()
    except BusPirateError as exc:
        return {"error": str(exc)}


def _i2c(bp: Any) -> Dict[str, Any]:
    with _open_i2c(bp, 100) as m:
        return {"devices": _found(m)}


def _onewire(bp: Any) -> Dict[str, Any]:
    return {"devices": onewire.search(bp)}


def _spi(bp: Any) -> Dict[str, Any]:
    with spi.open_spi(bp) as m:
        return spi.describe_jedec(SPIFlash(m).jedec_id())


def _action(bp: Any, opts: Dict[str, Any]) -> Dict[str, Any]:
    """Look for I2C devices, a 1-Wire device and an SPI flash chip, and name what answers."""
    result = {"i2c": _try(lambda: _i2c(bp)), "onewire": _try(lambda: _onewire(bp)),
              "spi": _try(lambda: _spi(bp))}  # type: Dict[str, Any]
    answered = [bus for bus in ("i2c", "onewire")
                if result[bus].get("devices")]
    if result["spi"].get("manufacturer"):
        answered.append("spi")
    result["answered"] = sorted(answered, key=("i2c", "onewire", "spi").index)
    if not answered:
        result["next"] = NEXT
    return result


register(Recipe(
    name="identify", title="Identify what is connected: I2C, 1-Wire and SPI in turn",
    words=("identify", "what is this", "unknown", "find", "detect", "probe", "what is connected"),
    bus="i2c", default_mv=0, min_mv=1200, max_mv=5000, pullups=True, wiring=WIRING,
    check=lambda bp, opts: {"ok": True}, action=_action, options={},
    source=DOCS + "command-reference/",
    notes=("wire the buses you suspect: I2C and 1-Wire share IO0, SPI uses IO4 to IO7",)))
