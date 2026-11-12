"""The sim-report recipe: a business summary of a SIM card, on the simulated SIM."""

import pytest

from buspirate.bp6.console import TerminalError
from buspirate.mcp.confirm import ConfirmStore
from buspirate.mcp.session import BoardSession
from buspirate.mcp_bp6 import engine
from buspirate.mcp_bp6.recipes import REGISTRY, find_recipes
from buspirate.mcp_bp6.recipes import sim as recipe_sim
from buspirate.mcp_bp6.recipes import smartcard
from buspirate.simulator_bp6 import make_sim

#: Files the report must never select: EF_ADN, EF_SMS, EF_MSISDN, EF_FDN,
#: EF_SDN, EF_LND (last numbers dialled) and the USIM phone book DF.
NEVER = {0x6F3A, 0x6F3C, 0x6F40, 0x6F3B, 0x6F49, 0x6F44, 0x5F3A}
KI = "secret key (Ki) and authentication keys — no SIM allows reading them"
SUMMARY_KEYS = {"operator", "country", "brand_on_phones", "iccid", "imsi", "card_type", "pin",
                "home_network", "equivalent_home_networks", "home_network_search",
                "capabilities", "capabilities_note", "preferred_roaming", "blocked_networks", "last_network",
                "access_class", "languages", "not_readable"}
ICCID = "89410112345678901231"
IMSI = "228011234567890"
NOTE = "what the SIM supports; the subscription itself may differ"
USIM_ONLY = ("VoLTE-ready (voice over LTE)", "SMS-over-IP-ready", "Wi-Fi-calling-ready",
             "NB-IoT-ready", "SUCI-ready (5G identity privacy)")


@pytest.fixture
def session():
    s = BoardSession(simulated="bp6")
    s.connect()
    yield s
    s.disconnect()


@pytest.fixture
def confirm():
    return ConfirmStore()


def _fake(session):
    return session.board.serial.owner


def _run(session, confirm, card):
    """Run sim-report on ``card``; check the clock and async print ended off either way."""
    fake = _fake(session)
    fake.sim = card
    plan = engine.plan_recipe(session, confirm, "sim-report", {"millivolts": 3000, "wait_s": 0.3})
    assert "error" not in plan, plan
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert fake.pwm == {} and not fake._hduart_printing  # clock and async print off
    assert b"\x03" not in bytes(fake.terminal.written)
    return out


def _report(session, confirm, card):
    out = _run(session, confirm, card)
    assert "error" not in out, out
    return out["result"]


def _ended_cleanly(fake):
    """The link's close went out: async print off (``]``), then the clock off (``g 1``)."""
    lines = [ln for ln in fake.lines_received() if ln != b"\r"]
    assert b"]\r" in lines and b"g 1\r" in lines[lines.index(b"]\r"):], lines[-6:]


def _aid_selects(card):
    return [a for a in card.apdus if a[1] == 0xA4 and a[2] == 0x04]


def _selected(card):
    """Every FID the card was asked to select (P1 00: by file ID)."""
    return [int.from_bytes(a[5:7], "big") for a in card.apdus
            if a[1] == 0xA4 and a[2] == 0x00 and len(a) == 7]


def _no_private_files(card):
    assert not NEVER & set(_selected(card)), _selected(card)
    assert {a[1] for a in card.apdus} <= {0xA4, 0xB0, 0xB2, 0xC0, 0xF2, 0x20}
    assert not [a for a in card.apdus if a[1] == 0x20 and len(a) > 5]  # no PIN ever sent


# -- the recipe ------------------------------------------------------------------

def test_sim_report_registered_like_smartcard_atr():
    r, atr = REGISTRY["sim-report"], REGISTRY["smartcard-atr"]
    assert (r.risk, r.transport, r.terminal_mode, r.bus) == ("none", "terminal", "hduart", "uart")
    assert r.terminal_flags == atr.terminal_flags == smartcard.TERMINAL_FLAGS
    assert r.wiring == atr.wiring == smartcard.WIRING
    assert r.source == atr.source
    assert (r.default_mv, r.min_mv, r.max_mv, r.milliamps) == (3000, 1800, 5000, 100)
    assert r.pullups is True and r.target_powered_ok is False
    assert r.options == {"clock_hz": 3_571_200, "wait_s": 1.0}
    assert find_recipes("sim")[0]["name"] == "sim-report"
    assert find_recipes("sim-report")[0]["name"] == "sim-report"


def test_sim_report_checks_the_clock(session, confirm):
    plan = engine.plan_recipe(session, confirm, "sim-report",
                              {"millivolts": 3000, "clock_hz": 900_000, "wait_s": 0.3})
    out = engine.run_recipe(session, confirm, plan["token"], {})
    assert out["check"]["ok"] is False and "clock_hz" in out["check"]["error"], out


# -- a GSM SIM, PIN off -------------------------------------------------------------

def test_gsm_sim_full_report(session, confirm):
    card = make_sim("gsm")
    result = _report(session, confirm, card)
    s = result["summary"]
    assert set(s) == SUMMARY_KEYS
    assert s["operator"] == "Swisscom"
    assert s["country"] == "Switzerland"
    assert s["brand_on_phones"] == "Swisscom"
    assert s["iccid"] == ICCID
    assert s["imsi"] == IMSI
    assert s["card_type"] == "SIM"
    assert s["pin"] == "off"
    assert s["home_network"] == "Swisscom (Switzerland)"
    assert s["equivalent_home_networks"] == ["Swisscom (Switzerland)"]
    assert s["home_network_search"] == "every 30 minutes while roaming"
    assert s["preferred_roaming"] == ["Telekom (Germany)", "SFR (France)",
                                      "an operator not in the table (Italy)"]
    assert s["blocked_networks"] == ["Sunrise (Switzerland)", "Salt (Switzerland)"]
    assert s["last_network"] == "Swisscom (Switzerland), 4G (LTE)"
    assert s["access_class"] == "ordinary subscriber (class 3)"
    assert s["languages"] == ["German", "English"]
    assert s["not_readable"] == [KI]
    for phrase in ("2G-ready (GSM)", "3G-ready (UMTS)", "4G-ready (LTE)", "5G-ready",
                   "mobile-data-ready (GPRS)", "MMS-ready (picture messages)",
                   "OTA-updatable (the operator can update the SIM over the air)"):
        assert phrase in s["capabilities"], s["capabilities"]
    assert not set(USIM_ONLY) & set(s["capabilities"])  # a GSM table cannot say so
    assert s["capabilities_note"] == NOTE
    raw = result["raw"]
    assert raw["ATR"] == card.atr.hex().upper()
    assert raw["EF_ICCID"] == "98141021436587092113"
    assert raw["EF_SPN"].startswith("00")
    assert {"EF_IMSI", "EF_AD", "EF_SST", "EF_HPLMNwAcT", "EF_EHPLMN", "EF_LOCI",
            "EF_PSLOCI", "EF_EPSLOCI", "EF_ACC", "EF_FPLMN", "EF_OPLMNwAcT"} <= set(raw)
    assert all(a[0] == 0xA0 for a in card.apdus)  # the GSM route throughout
    _no_private_files(card)


# -- a USIM that refuses class A0 (Review Focus 1) -------------------------------------

def test_usim_refusing_class_a0_takes_the_uicc_route(session, confirm):
    card = make_sim("usim")
    result = _report(session, confirm, card)
    s = result["summary"]
    assert set(s) == SUMMARY_KEYS
    assert card.apdus[0][0] == 0xA0 and all(a[0] == 0x00 for a in card.apdus[1:])
    assert any(a[1] == 0xA4 and a[2] == 0x04 for a in card.apdus)  # USIM selected by AID
    assert s["card_type"] == "USIM"
    assert (s["operator"], s["country"], s["iccid"], s["imsi"]) == (
        "Swisscom", "Switzerland", ICCID, IMSI)
    assert s["pin"] == "off"
    assert s["last_network"] == "Swisscom (Switzerland), 4G (LTE)"
    for phrase in ("4G-ready (LTE)", "5G-ready") + USIM_ONLY:
        assert phrase in s["capabilities"], s["capabilities"]
    assert s["capabilities_note"] == NOTE
    assert "EF_UST" in result["raw"] and "EF_DIR" in result["raw"]
    _no_private_files(card)


# -- a USIM that also answers class A0: the common real card (ruling 1) ----------------

def test_usim_answering_a0_is_read_through_the_usim(session, confirm):
    card = make_sim("usim-a0")
    result = _report(session, confirm, card)
    s = result["summary"]
    assert set(s) == SUMMARY_KEYS
    aid = _aid_selects(card)
    assert len(aid) == 1 and aid[0][0] == 0x00
    after = card.apdus[card.apdus.index(aid[0]):]
    assert all(a[0] == 0x00 for a in after)  # PIN status and network files in class 00
    assert 0x7F20 not in _selected(card)  # DF_GSM never used
    assert s["card_type"] == "USIM" and s["pin"] == "off"
    assert (s["operator"], s["imsi"]) == ("Swisscom", IMSI)
    for phrase in USIM_ONLY:
        assert phrase in s["capabilities"], s["capabilities"]
    assert "EF_UST" in result["raw"] and "EF_SST" not in result["raw"]
    _no_private_files(card)


def test_usim_listed_but_refused_falls_back_to_df_gsm(session, confirm):
    card = make_sim("usim-adf-refused")
    result = _report(session, confirm, card)
    s = result["summary"]
    assert set(s) == SUMMARY_KEYS
    assert len(_aid_selects(card)) == 1  # tried once, refused
    assert 0x7F20 in _selected(card)
    assert s["card_type"] == "SIM"  # the route actually taken
    assert (s["operator"], s["imsi"], s["pin"]) == ("Swisscom", IMSI, "off")
    assert "mobile-data-ready (GPRS)" in s["capabilities"]  # decoded as a GSM SST
    assert not set(USIM_ONLY) & set(s["capabilities"])
    assert "EF_SST" in result["raw"] and "EF_UST" not in result["raw"]
    _no_private_files(card)


def test_refuses_a0_and_lists_no_usim(session, confirm):
    card = make_sim("usim", without=(0x2F00,))
    s = _report(session, confirm, card)["summary"]
    assert set(s) == SUMMARY_KEYS
    assert not _aid_selects(card)
    assert s["iccid"] == ICCID
    assert s["operator"] == s["imsi"] == "not on this card"
    assert s["pin"] == "unknown (the card did not say)"
    assert s["not_readable"] == [KI]


def test_refuses_both_classes_is_one_clear_error(session, confirm):
    card = make_sim("gsm")
    card.classes = ()
    out = _run(session, confirm, card)
    assert "refuses both GSM (class A0) and UICC (class 00)" in out["error"], out
    assert len(card.apdus) == 2  # one SELECT MF per class, nothing more
    _ended_cleanly(_fake(session))


def test_error_mid_report_still_closes_the_link(session, confirm, monkeypatch):
    def boom(*args, **kwargs):
        raise TerminalError("decoder failed")

    monkeypatch.setattr(recipe_sim, "_summary", boom)
    out = _run(session, confirm, make_sim("gsm"))
    assert "decoder failed" in out["error"], out
    _ended_cleanly(_fake(session))


def test_card_pulled_mid_report_closes_the_link(session, confirm):
    card = make_sim("gsm")
    card.silent_after = 6
    out = _run(session, confirm, card)
    assert "stopped answering" in out["error"], out
    _ended_cleanly(_fake(session))


# -- the PIN is on -------------------------------------------------------------------------

def test_pin_on_lists_locked_fields(session, confirm):
    card = make_sim("pin-on")
    result = _report(session, confirm, card)
    s = result["summary"]
    assert set(s) == SUMMARY_KEYS
    assert s["pin"] == "on, 3 attempts left"
    assert s["iccid"] == ICCID and s["brand_on_phones"] == "Swisscom"
    assert s["imsi"] == "locked by the SIM PIN"
    assert s["blocked_networks"] == "locked by the SIM PIN"
    assert s["country"] == "Switzerland"  # from the card number, which needs no PIN
    assert s["operator"] == s["last_network"] == s["capabilities"] == "locked by the SIM PIN"
    assert s["capabilities_note"] == NOTE
    assert s["not_readable"][0] == KI
    locked = s["not_readable"][1:]
    assert "subscriber identity (IMSI): locked by the SIM PIN" in locked
    assert "blocked networks: locked by the SIM PIN" in locked
    assert "EF_IMSI" not in result["raw"]
    _no_private_files(card)


def test_capabilities_partly_locked_say_so(session, confirm):
    card = make_sim("pin-on")
    card.files[0x6F62]["chv1"] = False  # radio types readable, service table locked
    s = _report(session, confirm, card)["summary"]
    assert "4G-ready (LTE)" in s["capabilities"]
    assert s["capabilities_note"] == NOTE + "; more may be listed once the SIM PIN is given"


def test_empty_file_does_not_abort_the_report(session, confirm):
    card = make_sim("gsm")
    card.files[0x6F31]["data"] = b""  # EF_HPPLMN with no bytes
    s = _report(session, confirm, card)["summary"]
    assert s["home_network_search"] == "could not be read (the file is empty or malformed)"
    assert s["operator"] == "Swisscom"


def test_pin_blocked(session, confirm):
    card = make_sim("pin-on")
    card.attempts = 0
    assert _report(session, confirm, card)["summary"]["pin"] == "blocked"


# -- a file that is not there (Review Focus 2) ------------------------------------------

@pytest.mark.parametrize("profile", ["gsm", "usim"])
def test_missing_ehplmn_is_not_on_this_card(session, confirm, profile):
    card = make_sim(profile, without=(0x6FD9,))
    result = _report(session, confirm, card)
    s = result["summary"]
    assert s["equivalent_home_networks"] == "not on this card"
    assert s["operator"] == "Swisscom" and s["last_network"].startswith("Swisscom")
    assert "EF_EHPLMN" not in result["raw"]
    assert s["not_readable"] == [KI]


# -- build_report straight on a link ------------------------------------------------------

def test_capability_table_cites_services():
    for phrase, ust, sst, techs in recipe_sim.CAPABILITIES:
        assert phrase and (ust or sst or techs)
        assert all(n in recipe_sim.UST_SERVICES for n in ust)
        assert all(n in recipe_sim.SST_SERVICES for n in sst)
    assert not [p for p, *_ in recipe_sim.CAPABILITIES if "eSIM" in p]
