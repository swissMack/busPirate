"""Exception types raised by the Bus Pirate driver."""


class BusPirateError(Exception):
    """Base class for all driver errors."""


class ConnectionError(BusPirateError):
    """The serial port could not be opened or is not usable."""


class ModeError(BusPirateError):
    """The Bus Pirate would not enter or leave a mode."""


class ProtocolError(BusPirateError):
    """The Bus Pirate returned an unexpected or truncated response."""


class NackError(BusPirateError):
    """A target device did not acknowledge (I2C)."""


class UnsupportedFeatureError(BusPirateError):
    """The connected hardware or firmware does not have this feature."""


class ExternalVoltageError(BusPirateError):
    """A rail could not be connected because the pin already carries a voltage."""
