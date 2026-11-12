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
