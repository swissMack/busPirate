"""Switch to Web CLI: the app restarts the Bit Pirate into its browser terminal.

Firmware with ``webui start`` (firmware/bitpirate-1.8-webui-start.patch)
saves a one-shot flag and restarts; the next boot goes straight to WiFi
Connect, no button press. The board leaves USB as it restarts, so the app
lets go of the port and shows the address as a live link.
"""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web import webcli  # noqa: E402
from buspirate.web.server import create_app  # noqa: E402


@pytest.fixture
def client():
    with fastapi_testclient.TestClient(create_app(use_fake=True)) as c:
        yield c


def _run(client, panel, action, **params):
    return client.post("/api/run", json={"panel": panel, "action": action, "params": params})


def _connect_board(client):
    assert _run(client, "connection", "connect", port="simulated-bitpirate").status_code == 200


def _join(client):
    response = _run(client, "wifi", "connect", network="new", ssid="HomeNet", password="hunter2")
    assert response.status_code == 200, response.text


def _state(client):
    return client.get("/api/state").json()["status"]


def test_switching_restarts_the_board_and_lets_go_of_usb(client):
    _connect_board(client)
    _join(client)

    response = _run(client, "wifi", "web_cli")

    assert response.status_code == 200, response.text
    assert "Restarting into WiFi Connect on HomeNet" in response.text
    status = _state(client)
    assert status["connected"] is False
    assert status["web_cli"]["serving"] is True
    assert status["web_cli"]["ip"]


def test_the_board_is_told_webui_start(client):
    _connect_board(client)
    _join(client)
    fake = client.app.state.session.bp.serial

    _run(client, "wifi", "web_cli")

    assert "webui start" in fake.commands


def test_with_nothing_saved_it_says_so_and_stays_on_usb(client):
    _connect_board(client)

    response = _run(client, "wifi", "web_cli")

    assert response.status_code == 400, response.text
    assert "No network is saved on the board yet" in response.json()["error"]
    assert _state(client)["connected"] is True


def test_older_firmware_is_told_to_update_or_use_the_button(client):
    _connect_board(client)
    _join(client)
    client.app.state.session.bp.serial.webui_start = False  # v1.8 as released

    response = _run(client, "wifi", "web_cli")

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert "cannot switch to the Web CLI by itself" in error
    assert "short-press" in error
    assert _state(client)["connected"] is True


def test_reconnecting_over_usb_ends_serving(client):
    _connect_board(client)
    _join(client)
    _run(client, "wifi", "web_cli")

    _connect_board(client)

    assert not _state(client)["web_cli"].get("serving")


def test_waiting_for_the_page_stops_once_it_answers():
    answers = iter([False, False, True])

    assert webcli.wait_until_serving("192.168.1.80", timeout=5, interval=0,
                                     probe=lambda ip: next(answers)) is True


def test_waiting_for_the_page_gives_up_at_the_timeout():
    assert webcli.wait_until_serving("192.168.1.80", timeout=0.05, interval=0.01,
                                     probe=lambda ip: False) is False


def test_the_page_is_not_ready_while_it_says_nothing_matches():
    assert webcli.page_is_ready(200, "Nothing matches the given URI") is False
    assert webcli.page_is_ready(404, "") is False
    assert webcli.page_is_ready(200, "<html><title>Bit Pirate</title>") is True
