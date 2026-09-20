"""Raw-wire mode: the escape hatch for buses that are nearly SPI or I2C."""

import pytest

from buspirate import ModeError


def test_enters_and_leaves(bp, fake):
    with bp.rawwire() as raw:
        assert raw.version == 1
        assert fake.state == "rawwire"
    assert fake.state == "bbio"


def test_write_chunks_past_sixteen_bytes(bp, fake):
    with bp.rawwire() as raw:
        raw.write(bytes(20))
    assert b"\x1f" in bytes(fake.written)


def test_reads_bytes_and_bits(bp):
    with bp.rawwire() as raw:
        assert len(raw.read(3)) == 3
        assert raw.read_bit() in (0, 1)
        assert raw.peek_input() in (0, 1)


def test_manual_pin_control(bp, fake):
    with bp.rawwire() as raw:
        raw.set_clock(True)
        raw.set_data(False)
        raw.clock_tick()
    sent = bytes(fake.written)
    assert b"\x0b" in sent and b"\x0c" in sent and b"\x09" in sent


def test_configure_packs_its_flags(bp, fake):
    with bp.rawwire() as raw:
        fake.written.clear()
        raw.configure(push_pull=True, three_wire=True, lsb_first=False)
        assert fake.written[0] == 0x8C


def test_speed_is_validated(bp):
    with bp.rawwire() as raw:
        raw.set_speed(raw.SPEED_400KHZ)
        with pytest.raises(ValueError, match="SPEED_5KHZ"):
            raw.set_speed(7)


def test_raw_wire_is_exclusive_with_other_modes(bp):
    raw = bp.rawwire()
    with pytest.raises(ModeError, match="close it first"):
        bp.i2c()
    raw.close()
