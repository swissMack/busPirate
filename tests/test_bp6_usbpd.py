"""USB-PD plank (AP33772S): the status parser and the terminal helpers on the simulator."""

import pytest

from buspirate.bp6 import BusPirate6, usbpd
from buspirate.bp6.console import Reply, TerminalError
from buspirate.simulator_bp6 import FakeBp6

STATUS = """usbpd status
Source      : PD source connected
CC line     : CC1
Data role   : UFP
De-rating   : none
VBUS voltage: 5012 mV
VBUS current: 120 mA
Requested V : 5000 mV
Requested I : 3000 mA
Temperature : 31 C

Available PDO entries: 3
PDO 1 (SPR Fixed): 5000 mV, 0-3000 mA
PDO 2 (SPR Fixed): 9000 mV, 0-3000 mA, 150% peak
PDO 3 (SPR PPS): >=3300 mV to 21000 mV, 0-3000 mA
"""

THREE = [{"type": "Fixed", "mv": 5000, "ma": 3000},
         {"type": "Fixed", "mv": 9000, "ma": 3000},
         {"type": "PPS", "min": ">=3300 mV", "mv": 21000, "ma": 3000}]


def test_parse_status():
    st = usbpd.parse_status(STATUS)
    assert st["source"] == "PD source connected"
    assert (st["vbus_mv"], st["vbus_ma"], st["requested_mv"], st["requested_ma"],
            st["temperature_c"]) == (5012, 120, 5000, 3000, 31)
    assert st["pdos"] == [
        {"index": 1, "domain": "SPR", "type": "Fixed", "min_mv": 5000, "max_mv": 5000,
         "min_ma": 0, "max_ma": 3000},
        {"index": 2, "domain": "SPR", "type": "Fixed", "min_mv": 9000, "max_mv": 9000,
         "min_ma": 0, "max_ma": 3000},
        {"index": 3, "domain": "SPR", "type": "PPS", "min_mv": 3300, "max_mv": 21000,
         "min_ma": 0, "max_ma": 3000}]
    assert st["pdo_lines"][1] == "PDO 2 (SPR Fixed): 9000 mV, 0-3000 mA, 150% peak"


@pytest.mark.parametrize("desc,low", [
    (">=3300 mV", 3300), (">3300 mV and <=5000 mV", 5000), (">=15000 mV", 15000),
    (">15000 mV and <=20000 mV", 20000), ("reserved", 28000)])
def test_parse_pps_avs_minimum(desc, low):
    st = usbpd.parse_status("PDO 4 (EPR AVS): %s to 28000 mV, 0-5000 mA\n" % desc)
    assert st["pdos"] == [{"index": 4, "domain": "EPR", "type": "AVS", "min_mv": low,
                           "max_mv": 28000, "min_ma": 0, "max_ma": 5000}]


def test_parse_status_missing_fields():
    st = usbpd.parse_status("Source      : No source detected\n")
    assert st["source"] == "No source detected"
    assert st["vbus_mv"] is None and st["temperature_c"] is None and st["pdos"] == []


class _Says:
    """A console that answers every line with one fixed text."""

    def __init__(self, text):
        self.text, self.lines = text, []

    def command(self, line, timeout=3.0, answers=(), until=None):
        self.lines.append(line)
        return Reply(self.text, "I2C", None)


@pytest.mark.parametrize("call", [
    lambda con: usbpd.status(con),
    lambda con: usbpd.request(con, 1, None, None),
    lambda con: usbpd.reset(con)])
def test_failed_line_raises(call):
    with pytest.raises(TerminalError) as exc:
        call(_Says("Failed to refresh PDO list\n"))
    assert "Failed to refresh PDO list" in str(exc.value)


def test_reset_failed_raises():
    with pytest.raises(TerminalError):
        usbpd.reset(_Says("Failed to send PD hard reset\n"))


def test_request_line_has_only_the_flags_given():
    con = _Says("Requesting PDO 3, 12000mV @ 2000mA\nPD request accepted (PD_MSGRLT=0x01)\n"
                "Negotiated voltage: 12000 mV\nVBUS voltage: 11980 mV\n")
    out = usbpd.request(con, 3, 12000, 2000)
    assert con.lines == ["usbpd request -p 3 -v 12000 -i 2000"]
    assert out["accepted"] is True and out["result"] == "accepted"
    assert out["negotiated_mv"] == 12000 and out["vbus_mv"] == 11980
    usbpd.request(con, 1, None, None)
    assert con.lines[-1] == "usbpd request -p 1"


@pytest.fixture
def fake():
    board = FakeBp6()
    board.usbpd_pdos = [dict(p) for p in THREE]
    yield board


def make(fake):
    return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                      serial_factory=fake.factory(), reply_timeout=0.2, connect_timeout=0.1,
                      bpio2_settle=0.25, first_reply_timeout=0.4, drain_seconds=0.1)


def test_simulator_status_request_reset(fake):
    with make(fake).open().console() as con:
        con.command("m i2c -s 400")
        st = usbpd.status(con)
        assert st["source"] == "PD source connected" and len(st["pdos"]) == 3
        assert st["pdos"][2]["min_mv"] == 3300 and st["vbus_mv"] == 5000
        out = usbpd.request(con, 2, None, 3000)
        assert out["accepted"] is True and out["vbus_mv"] == 9000, out
        assert out["negotiated_mv"] == 9000
        assert usbpd.status(con)["requested_mv"] == 9000
        assert usbpd.reset(con) == {"sent": True}
        assert usbpd.status(con)["vbus_mv"] == 5000


def test_simulator_rejected(fake):
    fake.usbpd_result = "rejected"
    with make(fake).open().console() as con:
        con.command("m i2c -s 400")
        out = usbpd.request(con, 2, None, 3000)
    assert out["accepted"] is False and out["result"] == "rejected"
    assert out["negotiated_mv"] is None and out["vbus_mv"] == 5000


def test_simulator_invalid_index_raises(fake):
    with make(fake).open().console() as con:
        con.command("m i2c -s 400")
        with pytest.raises(TerminalError) as exc:
            usbpd.request(con, 9, None, None)
    assert "Invalid PDO index" in str(exc.value)


def test_simulator_no_source(fake):
    fake.usbpd_pdos = []
    with make(fake).open().console() as con:
        con.command("m i2c -s 400")
        st = usbpd.status(con)
    assert st["source"] == "No source detected" and st["pdos"] == []


def test_simulator_usbpd_only_in_i2c(fake):
    with make(fake).open().console() as con:
        reply = con.command("usbpd status")
    assert "Invalid command" in reply.text
