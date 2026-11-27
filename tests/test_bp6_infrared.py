"""The IR receive and send helpers against the simulated terminal."""

import pytest

from buspirate.bp6 import infrared
from buspirate.bp6.console import TerminalError
from buspirate.devices import ir


def test_constants():
    assert infrared.MAX_LINE == 256
    assert set(infrared.SENSORS) == {"38d", "56d", "38b"}


def test_send_air_too_long_raises_before_writing():
    class Boom:
        def command(self, *a, **k):
            raise AssertionError("must not write")
    air = ir.to_air(38, ir.encode_nec(1, 2))
    with pytest.raises(ValueError) as exc:
        infrared.send_air(Boom(), air)
    assert "256" in str(exc.value) and "ir-send-nec" in str(exc.value)


class _Con:
    def __init__(self, text, error=None):
        self.text, self.error, self.lines = text, error, []

    def command(self, line, timeout=3.0):
        from buspirate.bp6.console import Reply
        self.lines.append(line)
        return Reply(self.text, "INFRARED", self.error)


def test_send_air_parses_done():
    con = _Con("Transmitting from command line\n$38:1,2,;\n\nParsed AIR packet: modulation "
               "frequency 38kHz, 1 MARK/SPACE pairs\nTransmitting...done")
    assert infrared.send_air(con, "$38:1,2,") == {"sent": True, "carrier_khz": 38, "pairs": 1}
    assert con.lines == ["irtx $38:1,2,"]


def test_send_air_firmware_error():
    with pytest.raises(TerminalError, match="Unable to find end of MARK/SPACE"):
        infrared.send_air(_Con("Unable to find end of MARK/SPACE data (,) in AIR packet\n"
                               "Error parsing AIR packet"), "$38:1")


def test_send_code_needs_tx_line():
    assert infrared.send_code(_Con("\nTX: 0x0408.16 "), 0x408) == {"sent": True, "tx": "0x0408"}
    with pytest.raises(TerminalError, match="TX"):
        infrared.send_code(_Con("ERROR: command has no effect here"), 0x408)
