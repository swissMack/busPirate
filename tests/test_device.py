"""Device identification, capability gating and the bitbang extras."""

import pytest

from buspirate import UnsupportedFeatureError
from buspirate.device import (
    CAP_EXTENDED_AUX,
    CAP_PULLUP_VOLTAGE,
    CAP_SELF_TEST,
    parse_banner,
)
from buspirate.i2c import I2C
from tests.conftest import make_device
from tests.fake_serial import BANNERS, FakeSerial


# -- banner parsing --------------------------------------------------------


def test_parses_a_v3_banner():
    profile = parse_banner(BANNERS["v3"])
    assert profile.variant == "v3"
    assert profile.firmware == "v6.1"
    assert profile.bootloader == "v4.4"
    assert profile.devid == "0x0447"
    assert profile.has(CAP_SELF_TEST)
    assert not profile.has(CAP_PULLUP_VOLTAGE)


def test_parses_a_v4_banner():
    profile = parse_banner(BANNERS["v4"])
    assert profile.variant == "v4"
    assert profile.firmware == "v6.3-beta1"
    assert profile.has(CAP_PULLUP_VOLTAGE)
    assert profile.has(CAP_EXTENDED_AUX)
    # Binary self-test is v2go/v3 hardware only.
    assert not profile.has(CAP_SELF_TEST)


def test_an_unparseable_banner_is_not_fatal():
    profile = parse_banner("garbage from a noisy line")
    assert profile.variant == "unknown"
    assert not profile.has(CAP_PULLUP_VOLTAGE)
    assert not profile.has(CAP_SELF_TEST)
    assert "unidentified" in profile.describe()


def test_v2go_is_treated_as_a_v3():
    assert parse_banner("Bus Pirate v2go").variant == "v3"


def test_identify_runs_before_binary_mode(variant):
    fake = FakeSerial(variant=variant)
    with make_device(fake) as bp:
        assert bp.profile.variant == variant
        assert bp.is_open
    assert b"i\n" in bytes(fake.written)


def test_identification_can_be_skipped():
    fake = FakeSerial()
    device = make_device(fake)
    device.open(identify=False)
    try:
        assert device.profile.variant == "unknown"
        assert b"i\n" not in bytes(fake.written)
    finally:
        device.close()


# -- firmware-dependent tables --------------------------------------------


def test_firmware_before_v4_2_offers_only_two_i2c_speeds():
    profile = parse_banner("Bus Pirate v3.5\r\nFirmware v4.1 r559")
    assert sorted(profile.i2c_speeds) == [0, 1]


def test_modern_firmware_offers_four_i2c_speeds():
    profile = parse_banner(BANNERS["v3"])
    assert sorted(profile.i2c_speeds) == [0, 1, 2, 3]


def test_i2c_speed_error_lists_what_is_available():
    fake = FakeSerial(banner="Bus Pirate v3.5\r\nFirmware v4.1 r559\r\nHiZ>")
    with make_device(fake) as bp:
        with bp.i2c() as i2c:
            i2c.set_speed(1)
            with pytest.raises(ValueError, match=r"0=5kHz, 1=50kHz"):
                i2c.set_speed(I2C.SPEED_400KHZ)


# -- capability gating -----------------------------------------------------


def test_v4_only_commands_are_refused_on_a_v3():
    with make_device(FakeSerial(variant="v3")) as bp:
        with bp.i2c() as i2c:
            with pytest.raises(UnsupportedFeatureError, match="Bus Pirate v4"):
                i2c.set_pullup_voltage(I2C.PULLUP_3V3)
            with pytest.raises(UnsupportedFeatureError, match="Bus Pirate v4"):
                i2c.extended_aux(0x01)


def test_v4_only_commands_work_on_a_v4():
    fake = FakeSerial(variant="v4")
    with make_device(fake) as bp:
        with bp.i2c() as i2c:
            i2c.set_pullup_voltage(I2C.PULLUP_5V)
            i2c.extended_aux(0x10)
    assert b"\x52" in bytes(fake.written)


def test_self_test_is_refused_on_a_v4():
    with make_device(FakeSerial(variant="v4")) as bp:
        with pytest.raises(UnsupportedFeatureError, match="Bus Pirate v3"):
            bp.self_test()


def test_self_test_returns_the_error_count_on_a_v3():
    with make_device(FakeSerial(variant="v3")) as bp:
        assert bp.self_test() == 0


# -- measurement and PWM ---------------------------------------------------


def test_voltage_probe_converts_counts_to_volts(bp, fake):
    fake.voltage_counts = 512
    assert bp.read_voltage() == pytest.approx(3.3, abs=0.01)


def test_frequency_counter_reads_four_bytes(bp, fake):
    fake.frequency = 32_768
    assert bp.measure_frequency() == 32_768


def test_pwm_picks_a_prescaler_that_fits(bp, fake):
    bp.pwm(1000, duty_cycle=0.25)
    sent = bytes(fake.written)
    index = sent.rindex(b"\x12")
    prescaler, duty, period = sent[index + 1], sent[index + 2 : index + 4], sent[index + 4 : index + 6]
    assert prescaler == 0  # 1:1 reaches 1 kHz
    assert int.from_bytes(period, "big") == 15_999
    assert int.from_bytes(duty, "big") == pytest.approx(3_999, abs=1)


def test_pwm_uses_a_bigger_prescaler_for_slow_frequencies(bp, fake):
    bp.pwm(2)
    sent = bytes(fake.written)
    assert sent[sent.rindex(b"\x12") + 1] == 3  # 256:1


def test_pwm_rejects_an_impossible_frequency(bp):
    with pytest.raises(ValueError, match="outside the PWM range"):
        bp.pwm(0.01)


def test_pwm_rejects_a_silly_duty_cycle(bp):
    with pytest.raises(ValueError, match="duty_cycle"):
        bp.pwm(1000, duty_cycle=1.5)


# -- pins ------------------------------------------------------------------


def test_pin_state_round_trips_through_decode(bp):
    state = bp.set_pins(power=True, pullups=True, cs=True)
    assert bp.decode_pins(state) == {
        "power": True,
        "pullups": True,
        "aux": False,
        "mosi": False,
        "clk": False,
        "miso": False,
        "cs": True,
    }


# -- traffic hook ----------------------------------------------------------


def test_traffic_hook_sees_both_directions(bp):
    seen = []
    bp.add_traffic_hook(lambda direction, data: seen.append((direction, data)))
    bp.set_pins(power=True)
    assert ("tx", b"\xc0") in seen
    assert any(direction == "rx" for direction, _ in seen)


def test_a_broken_hook_cannot_break_the_bus(bp):
    def explode(direction, data):
        raise RuntimeError("bad observer")

    bp.add_traffic_hook(explode)
    assert bp.set_pins(power=True) == 0x40  # still works


def test_hooks_can_be_removed(bp):
    seen = []
    hook = lambda direction, data: seen.append(direction)  # noqa: E731
    bp.add_traffic_hook(hook)
    bp.set_pins()
    bp.remove_traffic_hook(hook)
    before = len(seen)
    bp.set_pins()
    assert len(seen) == before


# -- banner version tolerance ---------------------------------------------


def test_a_future_protocol_version_is_accepted():
    """A device answering BBIO2 / I2C2 must still work — the digit is a version."""

    class FutureFirmware(FakeSerial):
        def write(self, data):
            written = super().write(data)
            self._out = bytearray(
                bytes(self._out)
                .replace(b"BBIO1", b"BBIO2")
                .replace(b"I2C1", b"I2C2")
            )
            return written

    fake = FutureFirmware()
    with make_device(fake) as bp:
        assert bp.bitbang_version == 2
        with bp.i2c() as i2c:
            assert i2c.version == 2
            assert i2c.scan() == [0x50, 0x68]


def test_a_wrong_banner_explains_itself():
    class Confused(FakeSerial):
        def _state_bbio(self, cmd):
            if cmd == 0x02:
                self.state = "i2c"
                self._out += b"WHAT"
                return 1
            return super()._state_bbio(cmd)

    from buspirate import ModeError

    with make_device(Confused()) as bp:
        with pytest.raises(ModeError, match="resynchronise"):
            bp.i2c()


# -- supply rails and the v4 pull-up selector ------------------------------


def test_the_power_bit_switches_both_supplies_together(bp, fake):
    """There is no command to pick 3.3V or 5V — the bit enables both."""
    with bp.i2c() as i2c:
        fake.written.clear()
        i2c.configure_peripherals(power=True)
        assert fake.written[0] == 0x48  # 0b0100_1000, w=power only


def test_pullup_rail_selection_maps_to_the_documented_bits():
    fake = FakeSerial(variant="v4")
    with make_device(fake) as bp:
        with bp.i2c() as i2c:
            for selection, expected in ((I2C.PULLUP_OFF, 0x50), (I2C.PULLUP_3V3, 0x51), (I2C.PULLUP_5V, 0x52)):
                fake.written.clear()
                i2c.set_pullup_voltage(selection)
                assert fake.written[0] == expected


def test_pullup_rail_refuses_when_the_target_already_drives_vpu():
    from buspirate import ExternalVoltageError

    fake = FakeSerial(variant="v4")
    fake.vextern_powered = True
    with make_device(fake) as bp:
        with bp.i2c() as i2c:
            with pytest.raises(ExternalVoltageError, match="already present on the VPU"):
                i2c.set_pullup_voltage(I2C.PULLUP_5V)
            # Disconnecting is always allowed.
            i2c.set_pullup_voltage(I2C.PULLUP_OFF)


def test_pullup_rail_rejects_a_nonsense_selection():
    with make_device(FakeSerial(variant="v4")) as bp:
        with bp.i2c() as i2c:
            with pytest.raises(ValueError, match="PULLUP_OFF"):
                i2c.set_pullup_voltage(7)
