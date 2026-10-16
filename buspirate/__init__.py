"""A serial driver for the Bus Pirate v3/v4 binary ("bitbang") protocol.

Typical use::

    from buspirate import BusPirate

    with BusPirate("auto") as bp:
        print(bp.profile.describe())
        with bp.i2c() as i2c:
            i2c.configure_peripherals(power=True, pullups=True)
            i2c.set_speed(i2c.SPEED_100KHZ)
            print(i2c.scan())
"""

from .base import BusPirate
from .device import DeviceProfile, capabilities_for, parse_banner
from .exceptions import (
    BusPirateError,
    ConnectionError,
    ExternalVoltageError,
    ModeError,
    NackError,
    ProtocolError,
    UnsupportedFeatureError,
)
from .i2c import I2C
from .onewire import OneWire
from .ports import PortCandidate, discover, resolve
from .rawwire import RawWire
from .spi import SPI
from .uart import UART

__all__ = [
    "BusPirate",
    "BusPirateError",
    "ConnectionError",
    "DeviceProfile",
    "ExternalVoltageError",
    "I2C",
    "ModeError",
    "NackError",
    "OneWire",
    "PortCandidate",
    "ProtocolError",
    "RawWire",
    "SPI",
    "UART",
    "UnsupportedFeatureError",
    "capabilities_for",
    "discover",
    "parse_banner",
    "resolve",
]

# The one place the version lives: pyproject.toml reads it from here, the
# app build reads it from here, and the dashboard shows it in its top bar.
__version__ = "0.6.1"
