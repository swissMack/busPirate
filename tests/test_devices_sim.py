"""SIM file decoders: byte vectors coded as 3GPP TS 31.102 / TS 51.011 / TS 24.008 describe."""

import pkgutil

import pytest

from buspirate.devices import sim


def h(text):
    return bytes.fromhex(text.replace(" ", ""))


# -- ICCID -------------------------------------------------------------------

def test_iccid_19_digits_swapped_bcd_with_f_padding_and_luhn():
    got = sim.decode_iccid(h("98 14 10 21 43 65 87 09 21 F3"))
    assert got["iccid"] == "8941011234567890123"
    assert got["luhn_ok"] is True
    assert got["industry"] == "Telecommunications"
    assert got["country"] == "Switzerland"
    assert got["issuer_id"] == "01"


def test_iccid_20_digits_germany():
    got = sim.decode_iccid(h("98 94 20 00 00 21 43 65 87 29"))
    assert got["iccid"] == "89490200001234567892"
    assert got["luhn_ok"] is True
    assert got["country"] == "Germany"
    assert got["issuer_id"] == "02"


def test_iccid_bad_check_digit():
    got = sim.decode_iccid(h("98 14 10 21 43 65 87 09 21 F4"))
    assert got["iccid"] == "8941011234567890124"
    assert got["luhn_ok"] is False


def test_iccid_north_america_one_digit_calling_code():
    # 89 1 260 ... : calling code 1
    got = sim.decode_iccid(h("98 01 62 00 00 00 00 00 00 F0"))
    assert got["country"].startswith("North America")


def test_iccid_not_telecom():
    got = sim.decode_iccid(h("21 43 65 87 09 21 43 65 87 F9"))
    assert got["industry"] != "Telecommunications"
    assert got["country"] is None


# -- IMSI and EF_AD ----------------------------------------------------------

def test_mnc_digits_from_ef_ad():
    assert sim.mnc_digits(h("00 00 00 03")) == 3
    assert sim.mnc_digits(h("00 00 00 02")) == 2
    assert sim.mnc_digits(h("00 00 00")) == 2  # byte 4 absent (old SIM)
    assert sim.mnc_digits(b"") == 2
    assert sim.mnc_digits(h("00 00 00 FF")) == 2  # not a valid length
    assert sim.mnc_digits(h("00 00 00 13")) == 3  # upper bits RFU


def test_imsi_with_two_digit_mnc():
    got = sim.decode_imsi(h("08 29 82 10 21 43 65 87 09"), 2)
    assert got == {"imsi": "228011234567890", "mcc": "228", "mnc": "01", "msin": "1234567890"}
    assert sim.operator(got["mcc"], got["mnc"]) == "Swisscom"


def test_imsi_with_three_digit_mnc_uses_the_right_split():
    raw = h("08 39 01 14 10 32 54 76 98")  # 310410123456789
    three = sim.decode_imsi(raw, 3)
    assert three == {"imsi": "310410123456789", "mcc": "310", "mnc": "410", "msin": "123456789"}
    assert sim.operator(three["mcc"], three["mnc"]) == "AT&T"
    two = sim.decode_imsi(raw, 2)
    assert two["mnc"] == "41" and two["msin"] == "0123456789"
    assert sim.operator(two["mcc"], two["mnc"]) is None


def test_imsi_even_number_of_digits():
    got = sim.decode_imsi(h("08 31 01 14 10 32 54 76 F8"), 3)
    assert got["imsi"] == "31041012345678"


def test_imsi_unset_file():
    with pytest.raises(ValueError):
        sim.decode_imsi(h("FF FF FF FF FF FF FF FF FF"), 2)


# -- SPN -------------------------------------------------------------------

def test_spn_gsm_alphabet_with_padding():
    got = sim.decode_spn(h("01") + b"Swisscom" + b"\xff" * 8)
    assert got["name"] == "Swisscom"
    assert got["show_on_phone"] is True


def test_spn_not_shown_when_roaming():
    got = sim.decode_spn(h("02") + b"Salt" + b"\xff" * 12)
    assert got["name"] == "Salt"
    assert got["show_on_phone"] is False


def test_spn_gsm_specials_and_ucs2():
    assert sim.decode_spn(h("00 4F 32 20 5B 6E 64 65 72 FF"))["name"] == "O2 Änder"
    assert sim.decode_spn(h("00 80 00 53 00 FC 00 64 FF FF"))["name"] == "Süd"


def test_spn_empty():
    assert sim.decode_spn(h("FF") + b"\xff" * 16)["name"] == ""


# -- PLMN lists ----------------------------------------------------------------

def test_plmn_germany_01():
    got = sim.decode_plmn_list(h("62 F2 10"), with_act=False)
    assert got == [{"mcc": "262", "mnc": "01", "operator": "Telekom", "country": "Germany",
                    "technologies": []}]


def test_plmn_three_digit_mnc():
    got = sim.decode_plmn_list(h("13 00 14"), with_act=False)  # 310 410
    assert (got[0]["mcc"], got[0]["mnc"], got[0]["operator"]) == ("310", "410", "AT&T")


def test_plmn_empty_entries_are_skipped():
    got = sim.decode_plmn_list(h("FF FF FF 62 F2 10 FF FF FF"), with_act=False)
    assert [p["mnc"] for p in got] == ["01"]


def test_plmn_with_access_technology():
    data = h("22 F8 10 C0 80") + h("FF FF FF 00 00") + h("22 F8 20 08 00") + h("22 F8 30 00 80")
    got = sim.decode_plmn_list(data, with_act=True)
    assert [p["mnc"] for p in got] == ["01", "02", "03"]
    assert got[0]["technologies"] == ["2G (GSM)", "3G (UTRAN)", "4G (E-UTRAN)"]
    assert got[1]["technologies"] == ["5G (NG-RAN)"]
    assert got[2]["technologies"] == ["2G (GSM)"]
    assert got[0]["country"] == "Switzerland"


def test_plmn_unknown_operator_is_none():
    got = sim.decode_plmn_list(h("22 F8 99"), with_act=False)
    assert got[0]["mnc"] == "99" and got[0]["operator"] is None


# -- service tables --------------------------------------------------------

def test_ust_service_1_is_local_phone_book():
    got = sim.decode_service_table(h("01 00"), "ust")
    assert got[0] == {"number": 1, "name": "Local phone book", "enabled": True}
    assert got[1]["number"] == 2 and got[1]["enabled"] is False
    assert len(got) == 16


def test_ust_names_cover_1_to_120():
    for n in range(1, 121):
        assert sim.UST_SERVICES[n]
    got = sim.decode_service_table(h("00 00 00 00 00 00 00 00 00 00 10"), "ust")
    assert got[84] == {"number": 85, "name": "EPS (4G) mobility information", "enabled": True}


def test_sst_two_bits_per_service_allocated_and_activated():
    # service 1: allocated+activated (b1 b2), service 2: allocated only (b3),
    # service 3: activated only (b6, meaningless), service 4: both (b7 b8)
    got = sim.decode_service_table(h("E7"), "sst")
    assert [s["enabled"] for s in got] == [True, False, False, True]
    assert got[0]["name"] == "PIN disable function"
    assert got[3]["name"] == "Short message storage"


def test_sst_names_cover_1_to_56():
    for n in range(1, 57):
        assert sim.SST_SERVICES[n]


def test_service_table_unknown_kind():
    with pytest.raises(ValueError):
        sim.decode_service_table(b"\x01", "xyz")


# -- location files -------------------------------------------------------

def test_loci():
    got = sim.decode_loci(h("11 22 33 44 22 F8 10 12 34 FF 00"))
    assert got["network"] == {"mcc": "228", "mnc": "01", "operator": "Swisscom", "country": "Switzerland"}
    assert got["area_code"] == 0x1234
    assert got["technology"] == "2G/3G voice (circuit switched)"
    assert got["status"] == "updated"


def test_loci_never_registered():
    got = sim.decode_loci(h("FF FF FF FF FF FF FF FF FE FF 01"))
    assert got["network"] is None
    assert got["status"] == "not updated"


def test_psloci():
    got = sim.decode_psloci(h("11 22 33 44 AA BB CC 62 F2 10 00 2A 07 00"))
    assert got["network"]["operator"] == "Telekom"
    assert got["area_code"] == 0x002A
    assert got["routing_area"] == 7
    assert got["technology"] == "2G/3G data (packet switched)"
    assert got["status"] == "updated"


def test_epsloci():
    guti = h("0B F6 22 F8 10 80 01 02 11 22 33 44")
    tai = h("22 F8 10 AB CD")
    got = sim.decode_epsloci(guti + tai + h("02"))
    assert got["network"]["operator"] == "Swisscom"
    assert got["area_code"] == 0xABCD
    assert got["technology"] == "4G (LTE)"
    assert got["status"] == "roaming not allowed"


# -- ACC and EF_DIR ---------------------------------------------------------

def test_acc():
    assert sim.decode_acc(h("00 01")) == [0]
    assert sim.decode_acc(h("80 20")) == [5, 15]
    assert sim.decode_acc(h("01 00")) == [8]


def test_dir_usim_and_isim():
    usim = h("61 12 4F 10 A0 00 00 00 87 10 02 FF 33 FF 01 89 00 00 01 00") + h("FF" * 6)
    isim = h("61 18 4F 10 A0 00 00 00 87 10 04 FF 33 FF 01 89 00 00 01 00 50 04") + b"IMS!"
    empty = h("FF" * 26)
    got = sim.decode_dir([usim, isim, empty])
    assert got == [
        {"aid": "A0000000871002FF33FF018900000100", "application": "USIM (3G/4G/5G subscriber identity)"},
        {"aid": "A0000000871004FF33FF018900000100", "application": "ISIM (IMS, voice over LTE / Wi-Fi)",
         "label": "IMS!"},
    ]


def test_dir_unknown_application():
    got = sim.decode_dir([h("61 07 4F 05 A0 00 00 01 51")])
    assert got[0]["application"] == "Unknown application"


# -- tables -----------------------------------------------------------------

def test_country_and_operator_tables():
    assert sim.country("228") == "Switzerland"
    assert sim.country("262") == "Germany"
    assert sim.country("999") is None
    assert sim.operator("228", "01")
    assert sim.operator("228", "1") is None
    assert sim.operator("999", "99") is None


def test_tables_ship_in_the_package():
    # Loaded through the package, not a repo-relative path, so a wheel install has them.
    for name in ("mcc_mnc.csv", "calling_codes.csv", "LICENSE-Apache-2.0.txt"):
        data = pkgutil.get_data("buspirate.devices", "data/" + name)
        assert data
    first = pkgutil.get_data("buspirate.devices", "data/mcc_mnc.csv").decode("utf-8").splitlines()[0]
    assert first.startswith("#") and "Apache License 2.0" in first and "retrieved" in first


def test_tables_are_listed_as_package_data():
    import pathlib
    text = (pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    assert '"buspirate.devices" = ["data/*"]' in text
