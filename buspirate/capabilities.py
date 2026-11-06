"""Capability names, and what every Bus Pirate's binary protocol offers.

Kept apart from :mod:`buspirate.device` so the board definitions in
:mod:`buspirate.boards` can use them; ``device`` re-exports every name.
"""

from __future__ import annotations

from typing import Dict

# Capability names. Use the constants, not the strings.
CAP_SELF_TEST = "self_test"
CAP_PWM = "pwm"
CAP_ADC = "adc"
CAP_FREQUENCY = "frequency_count"
CAP_PULLUP_VOLTAGE = "pullup_voltage_select"
CAP_EXTENDED_AUX = "extended_aux"

# What every Bus Pirate's binary protocol offers and the ESP32 Bit Pirate's
# text command line does not. Offered to v3, v4 and unidentified boards alike,
# so nothing the dashboard showed a Bus Pirate before is hidden from it now.
CAP_BITBANG_PINS = "bitbang_pins"
CAP_SUPPLIES = "switchable_supplies"
CAP_ONEWIRE = "onewire"
CAP_RAWWIRE = "rawwire"
CAP_SNIFFER = "sniffer"
CAP_SPI_MODES = "spi_modes"
CAP_UART_BUFFERED = "uart_buffered_receive"
CAP_UART_BRIDGE = "uart_bridge"
CAP_SPI_FLASH_PROGRAM = "spi_flash_program"

# The Bus Pirate 6's programmable supply: set volts and a current limit, and
# read back what the target draws.
CAP_PSU_PROGRAMMABLE = "psu_programmable"
CAP_PSU_READOUT = "psu_current_readout"

BUS_PIRATE_ONLY = frozenset(
    {
        CAP_BITBANG_PINS,
        CAP_SUPPLIES,
        CAP_ONEWIRE,
        CAP_RAWWIRE,
        CAP_SNIFFER,
        CAP_SPI_MODES,
        CAP_UART_BUFFERED,
        CAP_UART_BRIDGE,
        CAP_SPI_FLASH_PROGRAM,
    }
)

# Which variant to name in an error when a capability is missing.
CAPABILITY_HOME: Dict[str, str] = {
    CAP_SELF_TEST: "Bus Pirate v3 (and v2go)",
    CAP_PULLUP_VOLTAGE: "Bus Pirate v4",
    CAP_EXTENDED_AUX: "Bus Pirate v3 with firmware v6.1 or newer",
    CAP_PSU_PROGRAMMABLE: "Bus Pirate 6",
    CAP_PSU_READOUT: "Bus Pirate 6",
    **{capability: "Bus Pirate v3 and v4" for capability in BUS_PIRATE_ONLY},
}

__all__ = [name for name in dir() if name.startswith("CAP_")] + [
    "BUS_PIRATE_ONLY", "CAPABILITY_HOME",
]
