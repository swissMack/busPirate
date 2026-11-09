"""The Bit Pirate's Web CLI address: read from its own replies, shown on top."""

import pytest

from buspirate.web.webcli import reply_drops_wifi, web_cli_address

# Controllers/WifiController.cpp, v1.8: handleConnect → handleWebUi over USB.
CONNECT_REPLY = [
    "WiFi: Connecting to HomeNet...",
    "",
    "WiFi: ✅ Connected successfully.",
    "",
    " [⚠️  WARNING] ",
    " If you're connected via serial,",
    " the web UI will not be active.",
    "WiFi Web UI: http://192.168.1.77 (reset and select WiFi Connect)",
]


def test_the_address_comes_from_the_connect_reply():
    assert web_cli_address(CONNECT_REPLY) == "192.168.1.77"


def test_the_address_comes_from_the_status_table():
    assert web_cli_address(["=== Wi-Fi Status ===", "Mode         : Station",
                            "IP           : 10.0.0.9", "Gateway      : 10.0.0.1"]) == "10.0.0.9"


def test_an_unconnected_status_has_no_address():
    assert web_cli_address(["IP           : 0.0.0.0", "Gateway      : 0.0.0.0"]) is None


def test_other_ip_lines_are_not_mistaken_for_it():
    assert web_cli_address(["Gateway      : 192.168.1.1", "DNS1         : 192.168.1.1",
                            "--- 8.8.8.8 ping statistics ---"]) is None


def test_disconnect_and_a_failed_connect_drop_the_wifi():
    assert reply_drops_wifi(["WiFi: Disconnected."])
    assert reply_drops_wifi(["WiFi: Connecting to X...", "WiFi: Connection failed."])
    assert not reply_drops_wifi(CONNECT_REPLY)


# -- through the dashboard --------------------------------------------------


@pytest.fixture
def client():
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from buspirate.web.server import create_app

    with fastapi_testclient.TestClient(create_app(use_fake=True)) as c:
        yield c


def _run(client, panel, action, **params):
    response = client.post("/api/run", json={"panel": panel, "action": action, "params": params})
    assert response.status_code == 200, response.text
    return response


def _web_cli(client):
    return client.get("/api/state").json()["status"]["web_cli"]


def _without_seen(info):
    """The address record minus its timestamp; on USB it is never serving."""
    assert info["seen"] > 0
    assert info["serving"] is False  # only Switch to Web CLI sets it (test_webui_start.py)
    return {k: v for k, v in info.items() if k not in ("seen", "serving")}


def test_no_address_until_the_board_has_joined_wifi(client):
    assert _web_cli(client) is None
    _run(client, "connection", "connect", port="simulated-bitpirate")
    assert _web_cli(client) is None


def test_joining_wifi_shows_the_address(client):
    _run(client, "connection", "connect", port="simulated-bitpirate")
    _run(client, "wifi", "connect", network="new", ssid="HomeNet", password="hunter2")
    assert _without_seen(_web_cli(client)) == {"ip": "192.168.1.77", "on_wifi": True, "simulated": True}


def test_wifi_status_shows_the_address_too(client):
    _run(client, "connection", "connect", port="simulated-bitpirate")
    _run(client, "wifi", "connect", network="new", ssid="HomeNet", password="hunter2")
    client.app.state.session.web_cli = None
    _run(client, "wifi", "status")
    assert _web_cli(client)["ip"] == "192.168.1.77"


def test_leaving_wifi_keeps_the_address_as_last_seen(client):
    _run(client, "connection", "connect", port="simulated-bitpirate")
    _run(client, "wifi", "connect", network="new", ssid="HomeNet", password="hunter2")
    _run(client, "wifi", "disconnect")
    assert _without_seen(_web_cli(client)) == {"ip": "192.168.1.77", "on_wifi": False, "simulated": True}


def test_unplugging_keeps_the_address_as_last_seen(client):
    _run(client, "connection", "connect", port="simulated-bitpirate")
    _run(client, "wifi", "connect", network="new", ssid="HomeNet", password="hunter2")
    _run(client, "connection", "disconnect")
    assert _without_seen(_web_cli(client)) == {"ip": "192.168.1.77", "on_wifi": False, "simulated": True}


# -- remembered across restarts ---------------------------------------------
# The app's window keeps no browser storage between launches, so the address
# is kept by the app itself, in BUSPIRATE_STATE_DIR (~/BusPirate by default).

from buspirate.web.session import DeviceSession  # noqa: E402

REPLY = ["WiFi Web UI: http://10.0.0.5 (reset and select WiFi Connect)"]


def test_a_real_boards_address_is_remembered_by_the_next_launch():
    DeviceSession().note_reply(REPLY)
    remembered = DeviceSession().status()["web_cli"]
    assert remembered["ip"] == "10.0.0.5"
    assert remembered["on_wifi"] is False  # last seen, not live
    assert remembered["seen"] > 0


def test_a_simulators_address_is_never_remembered():
    DeviceSession(use_fake=True).note_reply(REPLY)
    assert DeviceSession().status()["web_cli"] is None


def test_a_demo_launch_does_not_show_the_real_boards_address():
    DeviceSession().note_reply(REPLY)
    assert DeviceSession(use_fake=True).status()["web_cli"] is None


def test_an_unreadable_memory_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("BUSPIRATE_STATE_DIR", str(tmp_path))
    (tmp_path / "web-cli.json").write_text("{not json")
    assert DeviceSession().status()["web_cli"] is None
