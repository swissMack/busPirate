"""Sniffers and other streams: they take the port until stopped."""

import time

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web.decoders import make_decoder  # noqa: E402
from buspirate.web.server import create_app  # noqa: E402


@pytest.fixture
def client():
    app = create_app(use_fake=True, fake_variant="v3")
    with fastapi_testclient.TestClient(app) as client:
        client.post(
            "/api/run",
            json={"panel": "connection", "action": "connect", "params": {"port": ""}},
        )
        try:
            yield client
        finally:
            client.post("/api/stream/stop")


def run(client, panel, action, **params):
    response = client.post(
        "/api/run", json={"panel": panel, "action": action, "params": params}
    )
    return response.status_code, response.json()


def status(client):
    return client.get("/api/state").json()["status"]


def wait_for_events(client, at_least=1, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = status(client)["stream"]
        if current and current["events"] >= at_least:
            return current
        time.sleep(0.02)
    return status(client)["stream"]


# -- decoders --------------------------------------------------------------


def test_i2c_decoder_reads_a_whole_transaction():
    decoder = make_decoder("i2c-sniffer")
    events = decoder.feed(b"[\\\xa0+\\\x2a+]")
    assert [e["text"] for e in events] == ["START", "a0", "+", "2a", "+", "STOP"]


def test_i2c_decoder_survives_a_read_that_splits_an_escape():
    decoder = make_decoder("i2c-sniffer")
    first = decoder.feed(b"[\\")
    second = decoder.feed(b"\xa0+")
    assert [e["text"] for e in first] == ["START"]
    assert [e["text"] for e in second] == ["a0", "+"]


def test_spi_decoder_pairs_mosi_with_miso():
    decoder = make_decoder("spi-sniffer")
    events = decoder.feed(b"[\\\x9f\xff\\\x00\xef]")
    assert [e["text"] for e in events] == ["CS↓", "9f/ff", "00/ef", "CS↑"]
    assert events[1]["mosi"] == 0x9F and events[1]["miso"] == 0xFF


def test_voltage_decoder_holds_a_split_sample():
    decoder = make_decoder("voltage")
    assert decoder.feed(b"\x02") == []
    assert decoder.feed(b"\x00")[0]["volts"] == pytest.approx(3.3, abs=0.01)


def test_an_unknown_decoder_is_refused():
    with pytest.raises(ValueError, match="no decoder"):
        make_decoder("nope")


# -- the streaming lifecycle ----------------------------------------------


def test_starting_a_sniffer_takes_the_port(client):
    code, body = run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    assert code == 200, body
    assert body["result"]["render"] == "stream"
    assert body["result"]["decoder"] == "i2c-sniffer"
    assert "[ start" in body["result"]["legend"]
    assert status(client)["stream"]["kind"] == "I2C sniffer"


def test_a_running_sniffer_produces_decoded_events(client):
    run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    current = wait_for_events(client, at_least=5)
    assert current is not None and current["events"] >= 5


def test_other_actions_are_refused_while_a_sniffer_runs(client):
    run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    code, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert code == 400
    assert "has the port" in body["error"]


def test_stopping_returns_the_device_to_a_known_state(client):
    run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    wait_for_events(client, at_least=1)
    body = client.post("/api/stream/stop").json()
    assert body["result"]["stopped"] is True
    assert body["status"]["stream"] is None
    # Resynchronised to bitbang, so the next action re-enters cleanly.
    assert body["status"]["mode"] is None
    code, result = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert code == 200, result
    assert [item["label"] for item in result["result"]["items"]] == ["0x50", "0x68"]


def test_stopping_when_nothing_runs_says_so(client):
    body = client.post("/api/stream/stop").json()
    assert body["result"] == {"stopped": False, "reason": "nothing is streaming"}


def test_the_spi_sniffer_streams_too(client):
    code, body = run(
        client, "spi", "sniff", cs_low_only=True, power=False, speed=3, spi_mode=0
    )
    assert code == 200, body
    assert body["result"]["kind"] == "SPI sniffer"
    assert "10 MHz" in body["result"]["warning"]
    assert wait_for_events(client, at_least=3)["events"] >= 3


def test_the_voltage_monitor_streams(client):
    code, body = run(client, "pins", "voltage_stream")
    assert code == 200, body
    assert body["result"]["decoder"] == "voltage"
    assert wait_for_events(client, at_least=2)["events"] >= 2


def test_the_uart_bridge_warns_that_it_cannot_be_stopped(client):
    run(client, "uart", "configure", baud=10, framing=0, stop_bits=1, power=False)
    code, body = run(client, "uart", "bridge")
    assert code == 200, body
    assert "unplug" in body["result"]["warning"].lower()


def test_disconnecting_stops_a_running_sniffer(client):
    run(client, "i2c", "sniff", power=False, pullups=False, speed=2)
    wait_for_events(client, at_least=1)
    run(client, "connection", "disconnect")
    assert status(client)["connected"] is False


def test_the_bridge_action_asks_before_it_runs(client):
    panels = {p["id"]: p for p in client.get("/api/state").json()["panels"]}
    bridge = next(a for a in panels["uart"]["actions"] if a["name"] == "bridge")
    assert bridge["confirm"]
    assert bridge["stream"] is True


# -- the board's own terminal ----------------------------------------------


def test_the_terminal_holds_the_port_as_a_stream(client):
    code, body = run(client, "terminal", "open_terminal")
    assert code == 200, body
    assert body["result"]["input"] is True
    assert status(client)["stream"]["kind"] == "Board terminal"


def test_typing_into_the_terminal_reaches_the_board(client):
    run(client, "terminal", "open_terminal")
    code, body = run(client, "terminal", "send_line", line="i")
    assert code == 200, body
    found = wait_for_events(client, at_least=1)
    assert found["events"] >= 1


def test_send_line_is_refused_while_a_sniffer_runs(client):
    run(client, "i2c", "sniff", power=True, pullups=True, speed=2)
    code, body = run(client, "terminal", "send_line", line="i")
    assert code == 400
    assert "terminal" in body["error"]


def test_other_panels_are_refused_while_the_terminal_holds_the_port(client):
    run(client, "terminal", "open_terminal")
    code, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert code == 400


def test_leaving_the_terminal_returns_to_binary_with_nothing_held(client):
    run(client, "pins", "set_pins", power=True, pullups=False, aux=False,
        mosi=False, clk=False, miso=False, cs=False)
    run(client, "terminal", "open_terminal")
    assert client.post("/api/stream/stop").status_code == 200
    state = status(client)
    assert state["stream"] is None
    assert state["mode"] is None
    assert state["leds"]["VREG"] is False


def test_the_mode_led_goes_dark_in_the_terminal(client):
    assert status(client)["leds"]["MODE"] is True
    run(client, "terminal", "open_terminal")
    assert status(client)["leds"]["MODE"] is False


def test_the_mode_led_comes_back_after_the_terminal(client):
    run(client, "terminal", "open_terminal")
    client.post("/api/stream/stop")
    state = status(client)
    assert state["leds"]["MODE"] is True
    # The LED rule only looks at whether a TerminalState is currently
    # holding the port, so a stream that was simply cleared — without
    # binary mode actually having been restored — would satisfy it too.
    # Pin down the real claim being made: the session still believes it
    # has a working, connected device.
    assert state["connected"] is True


def test_a_failed_return_from_the_terminal_does_not_claim_a_mode(client, monkeypatch):
    from buspirate.base import BusPirate
    from buspirate.exceptions import ModeError

    run(client, "terminal", "open_terminal")

    def refuse(self, retries=25):
        raise ModeError("no BBIO response after 25 attempts on fake")

    monkeypatch.setattr(BusPirate, "enter_binary_mode", refuse)
    body = client.post("/api/stream/stop").json()

    state = body["status"]
    assert state["stream"] is None
    # A failed return must not go on claiming a working binary-mode
    # session — "mode" only exists in the connected branch of status(), so
    # its absence here is part of the honest answer, not an oversight.
    assert "mode" not in state
    assert state["connected"] is False
    assert state["leds"]["MODE"] is False
    # The reason has to actually reach the caller. Before this fix it only
    # ever reached the websocket "stream_stopped" event — invisible to an
    # HTTP-only caller like this test, which is exactly the gap: a note
    # nobody renders.
    assert "no BBIO response" in body["result"]["note"]

    # The board is presumed to be back in its own terminal, not a broken
    # binary session — reconnecting is the documented way back, and it
    # must actually work once the monkeypatch is no longer in effect.
    monkeypatch.undo()
    code, connect_body = run(client, "connection", "connect", port="")
    assert code == 200, connect_body
    assert status(client)["connected"] is True


def wait_for_no_stream(client, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if status(client)["stream"] is None:
            return True
        time.sleep(0.02)
    return status(client)["stream"] is None


def test_a_failed_write_in_the_terminal_does_not_wedge_the_session(
    client, monkeypatch
):
    """A cable pulled while typing must end the stream, not strand it.

    BusPirate.write raises on a dead handle. That write used to sit outside
    the reader loop's guards, so the exception escaped the loop and
    _finish_stream — the only thing that clears self.stream — never ran.
    The session then refused every later action with "…has the port"
    forever.
    """
    from buspirate.base import BusPirate

    run(client, "terminal", "open_terminal")
    assert status(client)["stream"]["kind"] == "Board terminal"

    original = BusPirate.write
    once = {"pending": True}

    def explode(self, data):
        if once["pending"]:
            once["pending"] = False
            raise OSError("device disconnected")
        return original(self, data)

    monkeypatch.setattr(BusPirate, "write", explode)
    code, body = run(client, "terminal", "send_line", line="i")
    assert code == 200, body

    assert wait_for_no_stream(client), "the stream was never finished"

    code, body = run(client, "connection", "connect", port="")
    assert "has the port" not in str(body), body
    assert code == 200, body


def test_a_terminal_that_fails_to_open_does_not_claim_binary_mode(
    client, monkeypatch
):
    """0x0F has gone out — the board is in its terminal whatever happens.

    If anything after reset_hardware() fails, no stream is ever started, so
    nothing else would tear the session down. Reporting a live binary-mode
    connection there is a lie about the hardware.
    """
    from buspirate.base import BusPirate

    def refuse(self):
        raise OSError("device disconnected during the settle")

    monkeypatch.setattr(BusPirate, "flush_input", refuse)
    code, body = run(client, "terminal", "open_terminal")
    assert code == 400, body

    state = status(client)
    assert state["stream"] is None
    assert state["connected"] is False
    # "mode" only exists in the connected branch of status(); its absence is
    # part of the honest answer.
    assert "mode" not in state

    monkeypatch.undo()
    code, connect_body = run(client, "connection", "connect", port="")
    assert code == 200, connect_body
    assert status(client)["connected"] is True
