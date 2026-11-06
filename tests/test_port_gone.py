"""A board that leaves USB mid-session: a plain message, then back to Connect.

Seen on a real ESP32 Bit Pirate (2026-11-06): it reset and came back on the
same /dev/cu.usbmodem… name, and every click after that answered "500". The
old handle's tcflush raised termios.error, which is not an OSError, so it
escaped every handler.
"""

import pytest

termios = pytest.importorskip("termios")

from buspirate.base import SerialLink  # noqa: E402
from buspirate.exceptions import BusPirateError, PortGoneError  # noqa: E402


class _DeadPort:
    def reset_input_buffer(self):
        raise termios.error(6, "Device not configured")

    def read(self, count):
        raise termios.error(6, "Device not configured")

    def write(self, data):
        raise OSError(6, "Device not configured")


def _link():
    link = SerialLink.__new__(SerialLink)
    link.serial = _DeadPort()
    link.port = "/dev/cu.usbmodemTEST"
    link._traffic_hooks = []
    return link


def test_a_dead_port_is_a_board_error_not_a_crash():
    with pytest.raises(PortGoneError) as caught:
        _link().flush_input()
    assert isinstance(caught.value, BusPirateError)
    assert "no longer answering" in str(caught.value)


def test_writing_to_a_dead_port_says_the_same():
    with pytest.raises(PortGoneError):
        _link().write(b"x")


# -- through the dashboard --------------------------------------------------


@pytest.fixture
def client():
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from buspirate.web.server import create_app

    with fastapi_testclient.TestClient(create_app(use_fake=True)) as c:
        yield c


def _run(client, panel, action, **params):
    return client.post("/api/run", json={"panel": panel, "action": action, "params": params})


def test_a_board_gone_mid_session_answers_plainly_and_drops_the_connection(client):
    assert _run(client, "connection", "connect", port="simulated-bitpirate").status_code == 200
    session = client.app.state.session
    session.bp.serial.reset_input_buffer = _DeadPort().reset_input_buffer
    session.bp.serial.read = _DeadPort().read

    response = _run(client, "wifi", "status")

    assert response.status_code == 400, response.text
    assert "no longer answering" in response.json()["error"]
    assert client.get("/api/state").json()["status"]["connected"] is False
    # And one Connect brings it back.
    assert _run(client, "connection", "connect", port="simulated-bitpirate").status_code == 200
