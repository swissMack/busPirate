import pytest

from buspirate import devices
from buspirate.exceptions import NackError, UnsupportedFeatureError
from buspirate.mcp.jobs import (
    NO_POWER_NOTE,
    frequency,
    i2c_read,
    i2c_scan,
    i2c_sensor,
    onewire_scan,
    pins_read_voltage,
    pwm,
    pwm_off,
    spi_identify,
    spi_sensor_read,
    spi_transfer,
    uart_listen,
    uart_send,
)
from buspirate.mcp.power import SOURCE_OWNER, plan_power
from buspirate.mcp.session import BoardGone, BoardSession
from buspirate.mode import Mode

ALL = ["v3", "v4", "bp6", "bitpirate"]


def connected(variant):
    s = BoardSession(simulated=variant)
    s.connect()
    return s


# -- I2C ------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL)
def test_i2c_scan_labels_devices(variant):
    s = connected(variant)
    result = i2c_scan(s)
    assert result["devices"] and all(d["label"] for d in result["devices"])
    assert result["power"] is False and "note" in result
    assert result["note"] == NO_POWER_NOTE


def test_i2c_scan_addresses_and_reading_bp6():
    result = i2c_scan(connected("bp6"))
    device = result["devices"][0]
    assert device["address"] == "0x76" and device["address_8bit"] == "0xEC/0xED"
    assert device["reading"]["device"] and device["reading"]["values"]
    assert result["speed_khz"] == 100


@pytest.mark.parametrize("asked, got", [(400, 400), (399, 100), (100, 100), (1, 5)])
def test_i2c_scan_speed_is_highest_not_above_request(asked, got):
    assert i2c_scan(connected("v3"), speed_khz=asked)["speed_khz"] == got


def test_i2c_scan_survives_a_chip_that_fails_to_measure(monkeypatch):
    def broken(bus, address):
        raise NackError("0x76 stopped answering")

    monkeypatch.setattr(devices, "read_i2c", broken)
    result = i2c_scan(connected("bp6"))
    assert result["devices"][0]["reading"] == {"error": "0x76 stopped answering"}


def test_eight_bit_address_refused():
    with pytest.raises(ValueError, match="0x50"):
        i2c_read(connected("v3"), 0xA0, 0, 1)


def test_reserved_address_refused():
    with pytest.raises(ValueError, match="0x08"):
        i2c_read(connected("v3"), 0x03, 0, 1)


def test_i2c_read_register_has_meaning():
    out = i2c_read(connected("bp6"), 0x76, 0xD0, 1)
    assert out["hex"] == "58" and out["meaning"]


def test_i2c_sensor_decodes_bp6():
    out = i2c_sensor(connected("bp6"), 0x76)
    assert out["device"] and out["values"]


def test_i2c_sensor_without_decoder():
    out = i2c_sensor(connected("v3"), 0x50)
    assert out["error"] == "no decoder for 0x50"


# -- SPI ------------------------------------------------------------------------

def test_spi_identify_bp6_has_capacity():
    out = spi_identify(connected("bp6"))
    assert out["capacity_bytes"] == 16777216
    assert out["jedec"] == "ef 40 18" and "Winbond" in out["manufacturer_device"]
    assert out["warning"] is None


def test_spi_identify_warns_on_ff():
    s = connected("v3")
    s.board.serial.spi_fill = 0xFF  # nothing driving MISO
    out = spi_identify(s)
    assert out["jedec"] == "ff ff ff"
    assert "not blank" in out["warning"] and out["capacity_bytes"] is None


def test_spi_transfer_reads_back():
    out = spi_transfer(connected("bp6"), "9f", 3)
    assert out["read_hex"] == "ef 40 18"


def test_spi_transfer_other_mode_needs_spi_modes():
    with pytest.raises(UnsupportedFeatureError):
        spi_transfer(connected("bitpirate"), "9f", 3, mode=2)


def test_spi_transfer_bad_hex():
    with pytest.raises(ValueError):
        spi_transfer(connected("v3"), "zz", 1)


def test_spi_sensor_unknown_lists_names():
    out = spi_sensor_read(connected("v3"), "nope")
    assert "error" in out and "MAX31855" in out["sensors"]


def test_spi_sensor_reads_values():
    out = spi_sensor_read(connected("v3"), "MAX31855")
    assert out["device"] == "MAX31855" and out["values"]


# -- UART -----------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL)
def test_uart_send(variant):
    out = uart_send(connected(variant), "hello")
    assert out["sent"] == "hello" and out["bytes"] == 5 and out["power"] is False


def test_uart_bad_baud_refused():
    with pytest.raises(ValueError, match="115200"):
        uart_send(connected("v3"), "x", baud=12345)


@pytest.mark.parametrize("variant", ALL)
def test_uart_listen(variant):
    out = uart_listen(connected(variant), seconds=0.1)
    assert "text" in out and "hex" in out


# -- 1-Wire and pins ------------------------------------------------------------

@pytest.mark.parametrize("variant", ["v3", "v4", "bp6"])
def test_onewire_scan_labels_rom(variant):
    out = onewire_scan(connected(variant))
    device = out["devices"][0]
    assert device["rom"].startswith("28 ") and "DS18B20" in device["label"]


def test_onewire_reading_bp6():
    out = onewire_scan(connected("bp6"))
    assert out["devices"][0]["reading"]["values"]


def test_pins_read_voltage_v3():
    out = pins_read_voltage(connected("v3"))
    assert isinstance(out["ADC_mv"], int) and out["ADC_mv"] > 0


def test_pins_need_capability():
    with pytest.raises(UnsupportedFeatureError):
        pins_read_voltage(connected("bp6"))


def test_pwm_and_frequency_v4():
    s = connected("v4")
    assert pwm(s, 1000, 0.25) == {"frequency_hz": 1000, "duty": 0.25, "power": False,
                                  "note": NO_POWER_NOTE}
    assert pwm_off(s)["pwm"] is False
    assert frequency(s)["hz"] == 1000


def test_pwm_duty_range():
    with pytest.raises(ValueError):
        pwm(connected("v3"), 1000, 25)


# -- power and unplug -----------------------------------------------------------

@pytest.fixture
def sent_peripherals(monkeypatch):
    """Every configure_peripherals a v3/v4 mode sends, as its keyword arguments."""
    seen = []
    original = Mode.configure_peripherals

    def record(self, **kwargs):
        seen.append(kwargs)
        return original(self, **kwargs)

    monkeypatch.setattr(Mode, "configure_peripherals", record)
    return seen


def test_power_reasserted_after_apply(sent_peripherals):
    s = connected("v3")
    s.power = plan_power("v3", 3300, SOURCE_OWNER)
    out = i2c_scan(s)
    assert out["power"] is True and "note" not in out
    assert sent_peripherals == [{"power": True, "pullups": True}]


def test_bus_tool_never_powers_unapproved_target(sent_peripherals):
    s = connected("v3")
    i2c_scan(s)
    spi_identify(s)
    onewire_scan(s)
    assert sent_peripherals and all(not k["power"] for k in sent_peripherals)


def test_unplug_mid_scan_raises_boardgone():
    s = connected("v3")

    def gone(*args, **kwargs):
        raise OSError(6, "Device not configured")

    s.board.serial.read = gone
    with pytest.raises(BoardGone):
        i2c_scan(s)
    assert s.board is None
