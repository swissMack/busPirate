"""Each board is described once, in buspirate.boards, and read from there.

The first tests record what every board did before the registry existed, so
moving its facts around cannot change them.
"""

import pytest

from buspirate import device as d

EXPECTED_CAPS = {
    # Its own modes and extra commands (step 3); none of the binary extras.
    "bitpirate": frozenset({d.CAP_CLI_EXTRAS, "cli_mode:onewire_cli", "cli_mode:dio",
                            "cli_mode:jtag", "cli_mode:wifi", "cli_mode:bluetooth"}),
    "bp6": frozenset({d.CAP_SUPPLIES, d.CAP_ONEWIRE, d.CAP_SPI_MODES, d.CAP_UART_BUFFERED,
                      d.CAP_SPI_FLASH_PROGRAM, d.CAP_PSU_PROGRAMMABLE, d.CAP_PSU_READOUT}),
    "v4": d.BUS_PIRATE_ONLY | {d.CAP_PWM, d.CAP_ADC, d.CAP_FREQUENCY, d.CAP_PULLUP_VOLTAGE},
    "v3": d.BUS_PIRATE_ONLY | {d.CAP_PWM, d.CAP_ADC, d.CAP_FREQUENCY, d.CAP_SELF_TEST,
                               d.CAP_EXTENDED_AUX},
    "unknown": d.BUS_PIRATE_ONLY | {d.CAP_PWM, d.CAP_ADC, d.CAP_FREQUENCY},
}


@pytest.mark.parametrize("variant", sorted(EXPECTED_CAPS))
def test_capabilities_are_unchanged(variant):
    assert d.capabilities_for(variant) == EXPECTED_CAPS[variant]


@pytest.mark.parametrize("variant, firmware, devid, text", [
    ("v3", "v6.1", None, "Bus Pirate v3, firmware v6.1"),
    ("v4", None, None, "Bus Pirate v4"),
    ("bitpirate", "1.8", None, "ESP32 Bit Pirate, firmware 1.8"),
    ("bp6", None, "hw 6.0", "Bus Pirate 6"),
    ("bp6", None, "hw 5.1", "Bus Pirate 5 (untested)"),
    ("unknown", None, None, "unidentified Bus Pirate"),
])
def test_descriptions_are_unchanged(variant, firmware, devid, text):
    assert d.DeviceProfile(variant=variant, firmware=firmware, devid=devid).describe() == text


def test_the_constants_are_also_in_their_own_module():
    from buspirate import capabilities as c

    assert c.CAP_ONEWIRE == d.CAP_ONEWIRE
    assert c.BUS_PIRATE_ONLY == d.BUS_PIRATE_ONLY
    assert c.CAPABILITY_HOME[c.CAP_SELF_TEST] == "Bus Pirate v3 (and v2go)"


# -- the registry -------------------------------------------------------------

from buspirate import boards  # noqa: E402


def test_the_registry_holds_the_four_boards_in_order():
    assert list(boards.REGISTRY) == ["v3", "v4", "bitpirate", "bp6"]
    assert all(b.variant == v for v, b in boards.REGISTRY.items())


def test_an_unknown_variant_gets_the_default_board_and_fallback_capabilities():
    assert boards.get("unknown").variant == "v3"
    assert boards.get(None).variant == "v3"
    assert boards.capabilities_for("unknown") == EXPECTED_CAPS["unknown"]


def test_device_reads_capabilities_from_the_registry(monkeypatch):
    import dataclasses

    fake = dataclasses.replace(boards.REGISTRY["v4"], capabilities=frozenset({"x"}))
    monkeypatch.setitem(boards.REGISTRY, "v4", fake)
    assert d.capabilities_for("v4") == frozenset({"x"})


def test_device_reads_board_names_from_the_registry(monkeypatch):
    import dataclasses

    fake = dataclasses.replace(boards.REGISTRY["v4"], name="Renamed")
    monkeypatch.setitem(boards.REGISTRY, "v4", fake)
    assert d.DeviceProfile(variant="v4").describe() == "Renamed"


def test_wiring_is_served_from_the_boards():
    from buspirate.web import wiring

    assert list(wiring.BOARDS) == list(boards.REGISTRY)
    for variant, board in boards.REGISTRY.items():
        assert wiring.BOARDS[variant] is board.wiring
        assert wiring.LED_RULES[variant] is board.led_rules
        assert wiring.LED_NOTES[variant] == board.led_note


# -- everything else reads the registry ---------------------------------------


@pytest.fixture
def client():
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from buspirate.web.server import create_app

    with fastapi_testclient.TestClient(create_app(use_fake=True)) as c:
        yield c


def test_the_guide_follows_each_boards_manual_and_page():
    from buspirate.web import docs

    assert boards.get(None).manual == "official"  # nothing connected
    assert boards.REGISTRY["bitpirate"].manual == "bitpirate-wiki"
    assert not hasattr(docs, "BOARD_PAGE")
    assert set(docs.MANUALS) == {b.manual for b in boards.REGISTRY.values()}


def test_simulators_and_terminal_captions_come_from_the_boards():
    from buspirate.web import session

    assert session.SIMULATED_VARIANTS == tuple(boards.REGISTRY)
    assert session.SIMULATED_NAMES == {v: b.simulated_name for v, b in boards.REGISTRY.items()}


def test_the_cli_offers_every_board(monkeypatch):
    from buspirate import cli

    parser = cli.build_parser()
    for action in parser._subparsers._group_actions[0].choices.values():
        for option in action._actions:
            if option.dest in ("variant", "fake_variant"):
                assert list(option.choices) == list(boards.REGISTRY)


def test_state_carries_the_board_names(client):
    labels = client.get("/api/state").json()["variant_labels"]
    assert labels == {v: b.name for v, b in boards.REGISTRY.items()}


def test_an_override_outside_the_registry_is_refused(client):
    response = client.post(
        "/api/run",
        json={"panel": "connection", "action": "set_variant", "params": {"variant": "v9"}},
    )
    assert response.status_code == 400


# -- step 2: one way around ----------------------------------------------------


@pytest.fixture
def client_bitpirate(client):
    response = client.post(
        "/api/run",
        json={"panel": "connection", "action": "connect", "params": {"port": "simulated-bitpirate"}},
    )
    assert response.status_code == 200, response.text
    return client


def test_text_traffic_drops_escapes_and_marks_line_breaks():
    from buspirate.web.session import traffic_text

    assert traffic_text(b"\rI2C> scan\x1b[K\r\nFound 0x68\r\n") == "⏎I2C> scan⏎Found 0x68⏎"
    assert traffic_text(b"\x00ok") == "·ok"


def test_only_text_boards_get_text_traffic():
    assert boards.REGISTRY["bitpirate"].traffic_text is True
    assert not any(b.traffic_text for v, b in boards.REGISTRY.items() if v != "bitpirate")


def test_a_bit_pirate_traffic_event_carries_its_text(client_bitpirate):
    response = client_bitpirate.post(
        "/api/run", json={"panel": "i2c", "action": "scan", "params": {}}
    )
    assert response.status_code == 200, response.text
    traffic = client_bitpirate.get("/api/state").json()["traffic"]
    assert any("scan" in entry.get("text", "") for entry in traffic)


def test_bus_pirate_traffic_stays_hex_only(client):
    client.post("/api/run", json={"panel": "connection", "action": "connect",
                                  "params": {"port": "simulated-v3"}})
    traffic = client.get("/api/state").json()["traffic"]
    assert traffic and not any("text" in entry for entry in traffic)


def test_a_bit_pirate_reads_as_text_from_its_first_byte(client_bitpirate):
    # The banner and prompt come before the board is identified.
    traffic = client_bitpirate.get("/api/state").json()["traffic"]
    assert traffic and all("text" in entry for entry in traffic)


def test_every_board_panel_doc_exists():
    from buspirate.web import docs

    for board in boards.REGISTRY.values():
        for page in board.panel_docs.values():
            assert docs.read(page) is not None, (board.variant, page)


def test_a_bit_pirate_panel_links_to_its_own_reference(client_bitpirate):
    panels = {p["id"]: p for p in client_bitpirate.get("/api/state").json()["panels"]}
    assert panels["i2c"]["doc"] == "bitpirate-wiki/05-i2c"
    assert panels["spi"]["doc"] == "bitpirate-wiki/06-spi"
    assert panels["uart"]["doc"] == "bitpirate-wiki/03-uart"
    assert panels["terminal"]["doc"] == "bitpirate-wiki/99-general"
    assert panels["connection"]["doc"] == "bitpirate"


def test_bus_pirate_panel_docs_are_unchanged(client):
    panels = {p["id"]: p for p in client.get("/api/state").json()["panels"]}
    assert panels["i2c"]["doc"] == "i2c"


# -- review fixes ---------------------------------------------------------------


def test_text_traffic_keeps_an_escape_split_across_reads_out():
    from buspirate.web.session import TextTraffic

    t = TextTraffic()
    assert t.feed(b"OK\x1b") == "OK"
    assert t.feed(b"[32mgreen") == "green"


def test_text_traffic_joins_a_character_split_across_reads():
    from buspirate.web.session import TextTraffic

    t = TextTraffic()
    assert t.feed(b"21.5 \xc2") == "21.5 "
    assert t.feed(b"\xb0C") == "°C"


@pytest.mark.parametrize("raw", [b"\x1b(Bx", b"\x1b[2~x", b"\x1b]0;title\x07x", b"\x1b7x"])
def test_text_traffic_drops_other_escape_forms(raw):
    from buspirate.web.session import TextTraffic

    assert TextTraffic().feed(raw) == "x"
