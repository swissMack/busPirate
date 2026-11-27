import pytest

from buspirate.devices import ir


def rc5_durations(address, command, toggle, s2=1):
    """Build a received RC5 frame (mark first, last space omitted) from fields."""
    bits = [1, s2, toggle]
    bits += [(address >> i) & 1 for i in range(4, -1, -1)]
    bits += [(command >> i) & 1 for i in range(5, -1, -1)]
    halves = []
    for b in bits:
        halves += [0, 1] if b else [1, 0]
    halves = halves[1:]  # leading space of S1=1 is invisible
    while halves and halves[-1] == 0:
        halves.pop()  # trailing space omitted
    out = []
    level, run = halves[0], 0
    for h in halves:
        if h == level:
            run += 1
        else:
            out.append(889 * run)
            level, run = h, 1
    out.append(889 * run)
    return out


def test_nec_roundtrip():
    assert ir.decode(ir.encode_nec(0x04, 0x08)) == {"protocol": "nec", "address": 4, "command": 8}


def test_nec_tolerates_jitter():
    frame = [int(d * 1.15) for d in ir.encode_nec(0x04, 0x08)]
    assert ir.decode(frame) == {"protocol": "nec", "address": 4, "command": 8}


def test_nec_bad_inverse_none():
    frame = ir.encode_nec(0x04, 0x08)
    frame[2 + 2 * 16 + 1] = 560 if frame[2 + 2 * 16 + 1] == 1690 else 1690
    assert ir.decode(frame) is None


def test_nec_extended_address():
    frame = ir.encode_nec(0x04, 0x08)
    frame[2 + 2 * 8 + 1] = 1690 if frame[2 + 2 * 8 + 1] == 560 else 560
    got = ir.decode(frame)
    assert got["extended"] is True and got["command"] == 8


def test_rc5_decode():
    got = ir.decode(rc5_durations(5, 12, 1))
    assert got == {"protocol": "rc5", "address": 5, "command": 12, "toggle": 1}


def test_rc5_decode_other_values():
    for a, c, t in ((0, 0, 0), (31, 63, 1), (17, 1, 0)):
        assert ir.decode(rc5_durations(a, c, t)) == {
            "protocol": "rc5", "address": a, "command": c, "toggle": t}


def test_rc5_s2_zero_sets_bit6():
    assert ir.decode(rc5_durations(5, 12, 0, s2=0))["command"] == 12 + 64


def test_garbage_none():
    assert ir.decode([]) is None
    assert ir.decode([100, 100, 100]) is None


def test_parse_air_two_frames():
    frames = ir.parse_air("$38:9000,4500,560,560,;\r\n\r\n$36:889,889,;\r\n")
    assert [f["carrier_khz"] for f in frames] == [38, 36]
    assert frames[0]["durations"] == [9000, 4500, 560, 560]


def test_to_air_no_semicolon():
    assert ir.to_air(38, [9000, 4500, 560]) == "$38:9000,4500,560,"


def test_to_air_limits():
    with pytest.raises(ValueError, match="127"):
        ir.to_air(38, [560] * 255)
    with pytest.raises(ValueError, match="20-60"):
        ir.to_air(70, [560])
