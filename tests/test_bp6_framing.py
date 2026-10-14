"""COBS framing for the Bus Pirate 6's BPIO2 port."""

import pytest

from buspirate.bp6.framing import FrameReader, cobs_decode, cobs_encode, frame


@pytest.mark.parametrize(
    "data",
    [b"", b"\x00", b"\x00\x00", b"\x11\x22\x00\x33", bytes(range(1, 255)),
     bytes(range(1, 256)), bytes(254) + b"\x01", b"\x01" * 600, bytes(range(256)) * 3],
)
def test_round_trip(data):
    encoded = cobs_encode(data)
    assert b"\x00" not in encoded
    assert cobs_decode(encoded) == data


def test_known_vectors():
    # From the COBS paper / Wikipedia examples.
    assert cobs_encode(b"\x00") == b"\x01\x01"
    assert cobs_encode(b"\x11\x22\x00\x33") == b"\x03\x11\x22\x02\x33"
    assert cobs_encode(b"\x11\x00\x00\x00") == b"\x02\x11\x01\x01\x01"


def test_a_malformed_frame_is_refused():
    with pytest.raises(ValueError):
        cobs_decode(b"\x05\x11")  # claims 4 bytes, has 1
    with pytest.raises(ValueError):
        cobs_decode(b"\x02\x00")  # a zero inside a frame


def test_frame_adds_one_delimiter():
    assert frame(b"\x11") == b"\x02\x11\x00"


def test_reader_splits_frames_across_chunks():
    reader = FrameReader()
    one, two = frame(b"abc"), frame(b"\x00de")
    stream = one + two
    assert reader.feed(stream[:3]) == []
    assert reader.feed(stream[3:]) == [one, two]


def test_reader_skips_empty_frames():
    reader = FrameReader()
    assert reader.feed(b"\x00\x00" + frame(b"x")) == [frame(b"x")]


def test_the_vendored_code_imports_as_a_package():
    from buspirate.bp6.bpio import ConfigurationRequest, ModeConfiguration  # noqa: F401
