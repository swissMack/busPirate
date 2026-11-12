"""The I2C and 2WIRE sniffer parsers."""

from buspirate.bp6 import sniff


def test_parse_i2c_default():
    assert sniff.parse_i2c("[ [0xA0]+ [0x00]+ [0x12]-]\r\n") == [
        {"address": 0x50, "read": False, "data": "00 12", "acks": "++-",
         "complete": True, "restarts": 0}]


def test_parse_i2c_restart_and_read():
    out = sniff.parse_i2c("[ [0xA0]+ [0x00]+ [ [0xA1]+ [0x34]-]\r\n")
    assert len(out) == 1
    assert out[0]["restarts"] == 1 and out[0]["address"] == 0x50
    assert out[0]["read"] is False and out[0]["data"] == "00 A1 34"


def test_parse_i2c_cut_off():
    out = sniff.parse_i2c("[ [0xA0]+ [0x00]+")
    assert len(out) == 1 and out[0]["complete"] is False


def test_parse_i2c_skips_u_lines():
    assert sniff.parse_i2c("U [0xA0]\r\n[ [0xA1]+ [0x01]-]\r\n")[0]["read"] is True
    assert len(sniff.parse_i2c("U [0xA0]\r\n[ [0xA1]+ [0x01]-]\r\n")) == 1


def test_parse_2wire():
    assert sniff.parse_2wire("[ 0x30 0x00 0xFF]\r\n") == [{"data": "30 00 FF", "complete": True}]


# -- PS/2 ---------------------------------------------------------------------

from buspirate.bp6 import ps2  # noqa: E402


def test_ps2_parse():
    text = ("[0x0000] t:0x00001234 D:0x1C\r\nMAKE_A --> a\r\n-----------\r\n"
            "[0x0001] t:0x00001240 D:0xF0\r\n[0x0002] t:0x00001241 D:0x1C\r\n"
            "BREAK_A --> a\r\n**********\r\nkey break tracker (limit 0x13F bytes): a\r\n"
            "**********\r\n-----------\r\n")
    out = ps2.parse(text)
    assert out["keys"] == ["MAKE_A", "BREAK_A"]
    assert out["typed"] == "a"
    assert out["packets"][0] == {"index": 0, "ms": 0x1234, "from": "keyboard", "byte": "1C"}
    assert len(out["packets"]) == 3 and out["dropped"] == 0


def test_ps2_parse_host_and_empty():
    out = ps2.parse("[0x0003] t:0x00000010 H:0xED\r\n")
    assert out["packets"][0]["from"] == "host" and out["typed"] == "" and out["keys"] == []


def test_ps2_dropped():
    text = ("\r\n!! ring buffer full, 3 packet(s) dropped !!\r\n"
            "\r\n!! ring buffer full, 4 packet(s) dropped !!\r\n")
    assert ps2.parse(text)["dropped"] == 7
