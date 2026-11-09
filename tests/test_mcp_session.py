import pytest

from buspirate.exceptions import PortGoneError
from buspirate.mcp.session import BoardGone, BoardSession, NotConnected


class _Cand:
    def __init__(self, port):
        self.device = port

    def likely_bus_pirate(self):
        return True


def _cand(port):
    return _Cand(port)


def test_connect_single_simulated():
    s = BoardSession(simulated="bp6")
    info = s.connect()
    assert info["connected"] and info["variant"] == "bp6"
    assert "psu_programmable" in info["capabilities"]
    s.disconnect()
    s.disconnect()
    assert s.board is None and s.capabilities == frozenset()


def test_two_boards_asks():
    s = BoardSession(discover=lambda include_unlikely=False: [_cand("/dev/a"), _cand("/dev/b")])
    assert s.connect() == {"connected": False, "choose_from": ["/dev/a", "/dev/b"]}
    assert s.board is None


def test_no_board():
    with pytest.raises(NotConnected):
        BoardSession(discover=lambda include_unlikely=False: []).connect()


def test_port_gone_drops_board():
    s = BoardSession(simulated="v3")
    s.connect()

    def boom(bp):
        raise PortGoneError("gone")

    with pytest.raises(BoardGone):
        s.run(boom)
    assert s.board is None


def test_peripherals_off_until_power_approved():
    s = BoardSession(simulated="v3")
    s.connect()
    assert s.peripherals() == {"power": False, "pullups": False}
    s.disconnect()


def test_run_without_board():
    with pytest.raises(NotConnected):
        BoardSession(simulated="v3").run(lambda bp: 1)


def test_busy_port_message():
    def opener(port):
        raise OSError(16, "Resource busy")

    s = BoardSession(opener=opener, discover=lambda include_unlikely=False: [_cand("/dev/a")])
    with pytest.raises(NotConnected, match="held by another program"):
        s.connect()
    assert s.board is None


def test_run_returns_value_and_disconnect_closes():
    closed = []

    class Dev:
        class profile:
            variant = "v4"
            capabilities = frozenset({"pwm"})

            @staticmethod
            def describe():
                return "x"

        def close(self):
            closed.append(1)

    s = BoardSession(opener=lambda p: Dev(), discover=lambda include_unlikely=False: [_cand("/dev/a")])
    assert s.connect()["port"] == "/dev/a"
    assert s.run(lambda bp: 7) == 7
    s.disconnect()
    assert closed == [1]
