"""Chips the app can name but not yet translate.

Add a line here to have a chip named in scan results. To have its readings
translated as well, give it a module of its own (see ``__init__.py``) and
take it out of this list.
"""

from __future__ import annotations

from . import Device


def _i2c(name: str, *addresses: int) -> Device:
    return Device(name, "i2c", addresses=addresses)


def _onewire(name: str, family: int) -> Device:
    return Device(name, "onewire", families=(family,))


DEVICES = [
    # -- I2C: by 7-bit address. Several chips can share one.
    _i2c("AK8963 magnetometer", 0x0C),
    _i2c("HMC5883L magnetometer", 0x1E),
    _i2c("PCF8574 / MCP23017 I/O expander", 0x20),
    _i2c("TSL2561 light sensor", 0x39),
    _i2c("SSD1306 OLED", 0x3C),
    _i2c("INA219 / HTU21D", 0x40),
    _i2c("ADS1115 / LM75 temperature", 0x48),
    _i2c("24Cxx EEPROM", 0x50, 0x51),
    _i2c("ADXL345 accelerometer", 0x53),
    _i2c("24Cxx EEPROM (or DS3231 NVRAM)", 0x57),
    _i2c("MLX90614 / CCS811", 0x5A),
    _i2c("DS1307 / DS3231 RTC, or MPU-6050", 0x68),
    _i2c("BMP180", 0x77),
    # -- 1-Wire: by family code, the first byte of the ROM.
    _onewire("DS1990A iButton", 0x01),
    _onewire("DS2438 battery monitor", 0x26),
    _onewire("DS2408 I/O", 0x29),
    _onewire("DS2431 EEPROM", 0x2D),
]

#: SPI flash makers, by the first byte of the JEDEC ID (command 0x9F).
JEDEC_MANUFACTURERS = {
    0x01: "Spansion / Cypress",
    0x1F: "Atmel / Adesto",
    0x20: "Micron / ST",
    0x37: "AMIC",
    0x9D: "ISSI",
    0xBF: "SST / Microchip",
    0xC2: "Macronix",
    0xC8: "GigaDevice",
    0xEF: "Winbond",
}
