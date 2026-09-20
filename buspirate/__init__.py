"""A serial driver for the Bus Pirate v3/v4 binary ("bitbang") protocol.

Typical use::

    from buspirate import BusPirate

    with BusPirate("/dev/tty.usbserial-A700eEoR") as bp:
        with bp.i2c() as i2c:
            i2c.configure_peripherals(power=True, pullups=True)
            i2c.set_speed(i2c.SPEED_100KHZ)
            print(i2c.scan())
"""

from .base import BusPirate
from .exceptions import (
    BusPirateError,
    ConnectionError,
    ModeError,
    NackError,
    ProtocolError,
)
from .i2c import I2C
from .onewire import OneWire
from .spi import SPI
from .uart import UART

__all__ = [
    "BusPirate",
    "BusPirateError",
    "ConnectionError",
    "ModeError",
    "NackError",
    "ProtocolError",
    "I2C",
    "SPI",
    "UART",
    "OneWire",
]

__version__ = "0.1.0"
