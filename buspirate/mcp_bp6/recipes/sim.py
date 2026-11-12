"""SIM card: a business summary of the card (``sim-report``). Read-only.

``sim-report-pin`` is the same report with the owner's SIM PIN, tried
exactly once on ``recipe_commit``, after its own yes, and never retried.

The report reads only operator and network files. It never selects the
phone book, text messages, the own phone number or call records (EF_ADN,
EF_SMS, EF_MSISDN, EF_FDN, EF_SDN, the logs), and :class:`SimLink` can send
nothing but SELECT, READ BINARY, READ RECORD, GET RESPONSE and STATUS.

Route: when EF_DIR lists a USIM application, the network files are read
through it (class ``00``, SELECT by AID); DF_GSM (class ``A0``, ``7F20``)
only when no USIM is listed or the card refuses that select.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from ...bp6.console import TerminalError
from ...bp6.sim import GSM_CLA, SELECT, UICC_CLA, SimLink, verify_line
from ...devices import sim as dec
from ...devices.sim import SST_SERVICES, UST_SERVICES  # noqa: F401  (cited by CAPABILITIES)
from . import Recipe, register
from .smartcard import OPTIONS, SOURCE, TERMINAL_FLAGS, WIRING, check_clock

Options = Dict[str, Any]

NOT_ON_CARD = "not on this card"
LOCKED = "locked by the SIM PIN"
UNREADABLE = "could not be read (the file is empty or malformed)"
#: What ``capabilities`` lists, and what it does not promise.
CAPABILITIES_NOTE = "what the SIM supports; the subscription itself may differ"
PARTLY_LOCKED = "; more may be listed once the SIM PIN is given"
NONE_RECORDED = "none recorded"
KI = "secret key (Ki) and authentication keys — no SIM allows reading them"

MF = 0x3F00
#: The file is not there: 6A 82 (UICC), 94 04 / 94 02 (GSM).
ABSENT = (0x6A82, 0x9404, 0x9402)
#: The file needs the PIN: 69 82 (UICC), 98 04 (GSM).
NEEDS_PIN = (0x6982, 0x9804)
#: The card does not take GSM class A0: class not supported, or instruction not supported.
REFUSED_CLASS = (0x6E00, 0x6D00)
#: The USIM application (ETSI TS 101 220 Annex E: RID A000000087, application code 1002).
USIM_AID_PREFIX = "A0000000871002"
#: EF_DIR records read at most.
MAX_RECORDS = 16

#: Files read without the application (raw name, FID, plain label).
MF_FILES = (
    ("EF_ICCID", 0x2FE2, "card serial number (ICCID)"),
    ("EF_DIR", 0x2F00, "applications on the card"),
    ("EF_PL", 0x2F05, "preferred languages"),
)
#: Files read under DF_GSM (7F20) or the USIM application, in this order.
APP_FILES = (
    ("EF_SPN", 0x6F46, "brand shown on phones"),
    ("EF_AD", 0x6FAD, "administrative data"),
    ("EF_IMSI", 0x6F07, "subscriber identity (IMSI)"),
    ("EF_SST", 0x6F38, "services the operator has switched on"),  # EF_UST on a USIM
    ("EF_HPPLMN", 0x6F31, "home network search interval"),
    ("EF_PLMNwAcT", 0x6F60, "your preferred networks"),
    ("EF_OPLMNwAcT", 0x6F61, "preferred roaming networks"),
    ("EF_HPLMNwAcT", 0x6F62, "home network radio types"),
    ("EF_EHPLMN", 0x6FD9, "equivalent home networks"),
    ("EF_FPLMN", 0x6F7B, "blocked networks"),
    ("EF_LOCI", 0x6F7E, "last network for calls"),
    ("EF_PSLOCI", 0x6F73, "last network for data"),
    ("EF_EPSLOCI", 0x6FE3, "last 4G network"),
    ("EF_ACC", 0x6F78, "access class"),
)

#: What the SIM is ready for, in plain words, in report order (readiness: the
#: subscription may not include it, see CAPABILITIES_NOTE). A phrase is
#: listed when any of its sources is on:
#:   USIM services: EF_UST bits, TS 31.102 §4.2.8 (names in ``devices.sim.UST_SERVICES``);
#:   GSM services: EF_SST, TS 51.011 §10.3.7 (``devices.sim.SST_SERVICES``);
#:   radio types: the access technology bits of the home network list
#:   (EF_HPLMNwAcT, TS 31.102 §4.2.5), as ``devices.sim.decode_plmn_list`` names them.
#: Only services that say so are used. No service says "eSIM" or "remote SIM
#: provisioning", so the report never claims it.
CAPABILITIES = (
    # phrase, UST services, SST services, radio types
    ("2G-ready (GSM)", (27,), (), ("2G (GSM)",)),               # UST 27 GSM access
    ("EC-GSM-IoT-ready", (), (), ("2G (EC-GSM-IoT)",)),
    ("3G-ready (UMTS)", (), (), ("3G (UTRAN)",)),
    ("4G-ready (LTE)", (85,), (), ("4G (E-UTRAN)",)),           # UST 85 EPS mobility information
    ("NB-IoT-ready", (121,), (), ("4G NB-IoT (E-UTRAN NB-S1)",)),  # UST 121 EARFCN list for MTC/NB-IoT
    ("5G-ready", (122, 123), (), ("5G (NG-RAN)",)),             # UST 122 5GS mobility, 123 5G security
    ("4G-by-satellite-ready", (), (), ("4G by satellite (E-UTRAN WB-S1)",
                                       "4G by satellite (E-UTRAN NB-S1)")),
    ("5G-by-satellite-ready", (), (), ("5G by satellite (NG-RAN)",)),
    ("mobile-data-ready (GPRS)", (), (38,), ()),                # SST 38 GPRS
    ("VoLTE-ready (voice over LTE)", (95,), (), ()),            # UST 95 UICC access to IMS
    ("SMS-over-IP-ready", (91,), (), ()),                       # UST 91 SMS over IP
    ("Wi-Fi-calling-ready", (106, 107), (), ()),                # UST 106/107 ePDG configuration
    ("Wi-Fi-emergency-calling-ready", (110, 111), (), ()),      # UST 110/111 ePDG for emergency
    ("eCall-ready (emergency calls from vehicles)", (89, 112), (), ()),  # UST 89 eCall, 112 IMS eCall
    ("SUCI-ready (5G identity privacy)", (124,), (), ()),       # UST 124 subscription identifier privacy
    ("MMS-ready (picture messages)", (52,), (57,), ()),         # UST 52 / SST 57 MMS
    ("OTA-updatable (the operator can update the SIM over the air)", (28,), (26,), ()),  # UST 28 / SST 26
)

#: Access classes 11 to 15 (3GPP TS 22.011 §4.2): special, high-priority users.
_SPECIAL_CLASSES = {11: "network operator use", 12: "security services", 13: "public utilities",
                    14: "emergency services", 15: "network operator staff"}

#: ISO 639-1 codes a SIM is likely to list (EF_PL / EF_ELP).
_LANGUAGES = {
    "ar": "Arabic", "cs": "Czech", "da": "Danish", "de": "German", "el": "Greek", "en": "English",
    "es": "Spanish", "fi": "Finnish", "fr": "French", "hu": "Hungarian", "it": "Italian",
    "ja": "Japanese", "ko": "Korean", "nl": "Dutch", "no": "Norwegian", "pl": "Polish",
    "pt": "Portuguese", "rm": "Romansh", "ru": "Russian", "sv": "Swedish", "tr": "Turkish",
    "zh": "Chinese",
}


# -- reading -------------------------------------------------------------------

def _shape(response: bytes, gsm: bool) -> Tuple[Optional[int], Optional[int]]:
    """(file size, record length or None for a transparent file) from a SELECT
    response: GSM bytes 3-4 / 14 / 15 (TS 51.011 §9.2.1), or the UICC FCP
    tags 80 and 82 (TS 102 221 §11.1.1.3). Size None: the card did not say."""
    if gsm:
        if len(response) < 15:
            return None, None
        size = response[2] << 8 | response[3]
        return size, (response[14] or None) if response[13] in (0x01, 0x03) else None
    fcp = dict(dec._tlv(response[2:])) if response[:1] == b"\x62" else {}
    size = int.from_bytes(fcp[0x80], "big") if fcp.get(0x80) else None
    desc = fcp.get(0x82, b"")
    record = None
    if len(desc) >= 4 and desc[0] & 0x07 in (0x02, 0x06):
        record = int.from_bytes(desc[2:4], "big") or None
    return size, record


class _Reader:
    """Reads files through a :class:`SimLink`; keeps each file's bytes or why it has none."""

    def __init__(self, link: SimLink) -> None:
        self.link = link
        self.data = {}  # type: Dict[str, Any]   # name -> bytes, or a list of records
        self.state = {}  # type: Dict[str, str]  # name -> NOT_ON_CARD / LOCKED / "could not ..."
        self.labels = {}  # type: Dict[str, str]

    @staticmethod
    def _why(sw: int) -> str:
        if sw in ABSENT:
            return NOT_ON_CARD
        if sw in NEEDS_PIN:
            return LOCKED
        return "could not be read (the card answered %04X)" % sw

    def mark(self, name: str, label: str, why: str) -> None:
        self.labels[name] = label
        self.state[name] = why

    def read(self, name: str, fid: int, label: str) -> None:
        self.labels[name] = label
        response, sw = self.link.select(fid)
        if sw != 0x9000:
            self.state[name] = self._why(sw)
            return
        size, record = _shape(response, self.link.cla == GSM_CLA)
        if record:
            count = min((size or record * MAX_RECORDS) // record, MAX_RECORDS)
            records = []
            for number in range(1, count + 1):
                data, sw = self.link.read_record(number, record)
                if sw != 0x9000:
                    break
                records.append(data)
            if not records and sw != 0x9000:
                self.state[name] = self._why(sw)
                return
            self.data[name] = records
            return
        out = bytearray()
        remaining = 256 if size is None else size
        while remaining > 0:
            data, sw = self.link.read_binary(min(remaining, 256), len(out))
            if sw != 0x9000:
                self.state[name] = self._why(sw)
                return
            out += data
            if size is None or not data:
                break
            remaining -= len(data)
        self.data[name] = bytes(out)

    def raw(self) -> Dict[str, str]:
        out = {}
        for name, value in self.data.items():
            joined = b"".join(value) if isinstance(value, list) else value
            out[name] = joined.hex().upper()
        return out

    def field(self, name: str) -> Optional[str]:
        """Why ``name`` has no data (NOT_ON_CARD, LOCKED, ...), or None when it has."""
        return None if name in self.data else self.state.get(name, NOT_ON_CARD)


def _decoded(reader: _Reader, name: str, decode: Any) -> Tuple[Any, Optional[str]]:
    """(the decoded file, None) or (None, why there is nothing)."""
    why = reader.field(name)
    if why is not None:
        return None, why
    try:
        return decode(reader.data[name]), None
    except (ValueError, IndexError):
        return None, UNREADABLE


# -- wording -------------------------------------------------------------------

def _network_name(network: Dict[str, Any]) -> str:
    where = network.get("country") or "an unknown country"
    if network.get("operator"):
        return "%s (%s)" % (network["operator"], where)
    return "an operator not in the table (%s)" % where


def _names(networks: List[Dict[str, Any]]) -> List[str]:
    out = []  # type: List[str]
    for network in networks:
        name = _network_name(network)
        if name not in out:
            out.append(name)
    return out


def _pin_text(status: Dict[str, Any]) -> str:
    if status.get("blocked"):
        return "blocked"
    if status.get("needed") is False:
        return "off"
    if status.get("needed"):
        left = status.get("attempts_left")
        return "on, %d attempt%s left" % (left, "" if left == 1 else "s")
    return "unknown (the card did not say)"


def _access_class(classes: List[int]) -> str:
    ordinary = [c for c in classes if c < 10]
    special = ["class %d (%s)" % (c, _SPECIAL_CLASSES[c]) for c in classes if c in _SPECIAL_CLASSES]
    parts = []
    if ordinary:
        parts.append("ordinary subscriber (class%s %s)"
                     % ("es" if len(ordinary) > 1 else "", ", ".join(str(c) for c in ordinary)))
    if special:
        parts.append("priority access: " + ", ".join(special))
    return "; ".join(parts) or "no access class set"


def _languages(data: bytes) -> List[str]:
    out = []
    for i in range(0, len(data) - 1, 2):
        pair = data[i:i + 2]
        if pair == b"\xff\xff" or not pair.isalpha():
            continue
        code = pair.decode("ascii").lower()
        out.append(_LANGUAGES.get(code, code))
    return out


def _last_network(reader: _Reader) -> str:
    found = []
    why = []
    for name, decode in (("EF_EPSLOCI", dec.decode_epsloci), ("EF_PSLOCI", dec.decode_psloci),
                         ("EF_LOCI", dec.decode_loci)):
        value, reason = _decoded(reader, name, decode)
        if value is None:
            why.append(reason)
        elif value["network"] is not None:
            found.append(value)
    if found:
        # The newest technology whose registration is current; else the newest one known.
        best = min(found, key=lambda v: v["status"] != "updated")
        return "%s, %s" % (_network_name(best["network"]), best["technology"])
    return LOCKED if LOCKED in why else NONE_RECORDED


def _capabilities(reader: _Reader, gsm: bool) -> Tuple[Any, str]:
    """(the readiness phrases, or LOCKED; the note that goes with them).

    ``gsm``: the service table is a GSM SST (read under DF_GSM), not a USIM UST.
    """
    services, why_services = _decoded(reader, "EF_SST",
                                      lambda b: dec.decode_service_table(b, "sst" if gsm else "ust"))
    home, why_home = _decoded(reader, "EF_HPLMNwAcT", lambda b: dec.decode_plmn_list(b, True))
    locked = LOCKED in (why_services, why_home)
    if services is None and home is None and locked:
        return LOCKED, CAPABILITIES_NOTE
    on = {s["number"] for s in services or () if s["enabled"]}
    radio = {t for network in home or () for t in network["technologies"]}
    out = []
    for phrase, ust, sst, techs in CAPABILITIES:
        if on & set(sst if gsm else ust) or radio & set(techs):
            out.append(phrase)
    return out, CAPABILITIES_NOTE + (PARTLY_LOCKED if locked else "")


# -- the report ----------------------------------------------------------------

def _route(link: SimLink) -> Tuple["_Reader", bool, Dict[str, Any], int]:
    """Read the card files and take the route to the network files.

    Returns the reader (EF_ICCID, EF_DIR, EF_PL read), whether the USIM is
    used, the PIN status from that route, and the status word of reaching the
    network files (``90 00``: reached). The link is left in the route's class
    with its application (or DF_GSM) selected, ready for the PIN.
    Raises ``TerminalError`` when the card refuses both classes.
    """
    link.cla = GSM_CLA
    _, sw = link.select(MF)
    answers_gsm = sw not in REFUSED_CLASS
    if not answers_gsm:
        link.cla = UICC_CLA
        _, sw = link.select(MF)
        if sw in REFUSED_CLASS:
            raise TerminalError("the card refuses both GSM (class A0) and UICC (class 00) "
                                "commands (it answered %04X): it does not look like a SIM" % sw)
    reader = _Reader(link)
    for name, fid, label in MF_FILES:
        reader.read(name, fid, label)

    apps, _ = _decoded(reader, "EF_DIR", dec.decode_dir)
    usim = next((a for a in apps or () if a["aid"].startswith(USIM_AID_PREFIX)), None)
    pin = {}  # type: Dict[str, Any]
    through_usim = False
    reach = 0x6A82  # neither route: the network files are not on this card
    if usim is not None:
        link.cla = UICC_CLA
        _, reach = link.command(UICC_CLA, SELECT, 0x04, 0x04, bytes.fromhex(usim["aid"]))
        through_usim = reach == 0x9000
    if through_usim:
        pin = link.pin_status()
    elif answers_gsm:
        link.cla = GSM_CLA
        pin = link.pin_status()  # selects DF_GSM
        reach = 0x9000 if pin["sw"] == "9000" else int(pin["sw"], 16)
    return reader, through_usim, pin, reach


def build_report(link: SimLink) -> Dict[str, Any]:
    """Read the card's operator and network files and summarise them in plain words.

    The card files (EF_ICCID, EF_DIR, EF_PL) are read with class ``A0``, or
    class ``00`` when the card refuses ``A0`` (``6E 00`` / ``6D 00``). When
    EF_DIR lists a USIM application, the network files are read through it
    (class ``00``, SELECT by AID); DF_GSM (class ``A0``, ``7F20``) is used only
    when no USIM is listed or the card refuses that select. The summary has
    the same keys either way; the file bytes are under ``raw``.

    Raises ``TerminalError`` when the card refuses both classes.
    """
    return _build(link)[0]


def _build(link: SimLink) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """:func:`build_report`, and the PIN status it read on the way."""
    reader, through_usim, pin, reach = _route(link)
    for name, fid, label in APP_FILES:
        if reach == 0x9000:
            reader.read(name, fid, label)
        else:
            reader.mark(name, label, reader._why(reach))

    summary = _summary(reader, through_usim, pin)
    raw = {"ATR": link.atr_bytes.hex().upper()}
    raw.update(reader.raw())
    if through_usim and "EF_SST" in raw:
        raw["EF_UST"] = raw.pop("EF_SST")  # 6F38 is the USIM service table under the USIM
    return {"summary": summary, "raw": raw}, pin


def _summary(reader: _Reader, through_usim: bool, pin: Dict[str, Any]) -> Dict[str, Any]:
    iccid, why_iccid = _decoded(reader, "EF_ICCID", dec.decode_iccid)
    ad = reader.data.get("EF_AD", b"")
    imsi, why_imsi = _decoded(reader, "EF_IMSI", lambda b: dec.decode_imsi(b, dec.mnc_digits(ad)))
    spn, why_spn = _decoded(reader, "EF_SPN", dec.decode_spn)
    search, why_search = _decoded(reader, "EF_HPPLMN", lambda b: b[0])
    ehplmn, why_ehplmn = _decoded(reader, "EF_EHPLMN", lambda b: dec.decode_plmn_list(b, False))
    roaming, why_roaming = _decoded(reader, "EF_OPLMNwAcT", lambda b: dec.decode_plmn_list(b, True))
    blocked, why_blocked = _decoded(reader, "EF_FPLMN", lambda b: dec.decode_plmn_list(b, False))
    acc, why_acc = _decoded(reader, "EF_ACC", dec.decode_acc)
    languages, why_languages = _decoded(reader, "EF_PL", _languages)

    if imsi is not None:
        home = {"operator": dec.operator(imsi["mcc"], imsi["mnc"]),
                "country": dec.country(imsi["mcc"])}  # type: Optional[Dict[str, Any]]
    else:
        home = None
    if home is not None:
        operator = home["operator"] or "not in the operator table"
        country = home["country"] or "an unknown country"
    else:
        operator = why_imsi
        country = (iccid or {}).get("country") or why_imsi

    capabilities, capabilities_note = _capabilities(reader, gsm=not through_usim)
    if search is None:
        search_text = why_search
    elif search == 0:
        search_text = "never searches for home while roaming"
    else:
        search_text = "every %d minutes while roaming" % (search * 6)

    not_readable = [KI]
    for name, _, label in MF_FILES + APP_FILES:
        why = reader.state.get(name)
        if why is not None and why != NOT_ON_CARD:
            not_readable.append("%s: %s" % (label, why))

    return {
        "operator": operator,
        "country": country,
        "brand_on_phones": why_spn or (spn["name"] or "none set"),
        "iccid": why_iccid or iccid["iccid"],
        "imsi": why_imsi or imsi["imsi"],
        "card_type": "USIM" if through_usim else "SIM",
        "pin": _pin_text(pin),
        "home_network": _network_name(home) if home is not None else why_imsi,
        "equivalent_home_networks": why_ehplmn or _names(ehplmn) or "none set",
        "home_network_search": search_text,
        "capabilities": capabilities,
        "capabilities_note": capabilities_note,
        "preferred_roaming": why_roaming or _names(roaming),
        "blocked_networks": why_blocked or _names(blocked),
        "last_network": _last_network(reader),
        "access_class": why_acc or _access_class(acc),
        "languages": why_languages or languages,
        "not_readable": not_readable,
    }


# -- the recipe ------------------------------------------------------------------

def _report(con: Any, opts: Options) -> Dict[str, Any]:
    """Read a SIM card and summarise it: operator, country, identities and what is switched on."""
    link = SimLink.open(con, opts["clock_hz"], atr_wait_s=float(opts["wait_s"]))
    # The context manager closes the link (async print off, clock off) on every path.
    with link:
        return build_report(link)


register(Recipe(
    name="sim-report",
    title="SIM card: a business summary (operator, country, identities, what is switched on)",
    words=("sim", "sim card", "simcard", "usim", "operator", "imsi", "iccid", "mobile", "report"),
    bus="uart", transport="terminal", terminal_mode="hduart", terminal_flags=TERMINAL_FLAGS,
    default_mv=3000, min_mv=1800, max_mv=5000, milliamps=100, pullups=True,
    target_powered_ok=False, options=dict(OPTIONS),
    check=check_clock, action=_report, wiring=WIRING,
    notes=("read-only: it reads the operator and network files only, never contacts, text "
           "messages, the phone number or call records, and never sends a PIN",
           "3 V suits most SIMs; an old 5 V-only SIM needs 5000 mV"),
    source=SOURCE))


# -- the PIN, once, on its own yes (sim-report-pin) ----------------------------------

PIN_HINT = ("a PIN attempt may have been used: run sim-report to see how many attempts "
            "are left")
NO_RERUN = ("sim-report-pin does not keep the PIN for a re-run; give the PIN again with a "
            "fresh plan")
NOTHING_SENT = "nothing was sent to the SIM's PIN; run sim-report to read what needs no PIN"
_PIN_RE = re.compile(r"[0-9]{4,8}")


def _attempts(n: int) -> str:
    return "%d attempt%s" % (n, "" if n == 1 else "s")


def _pin_refusal(pin: Dict[str, Any]) -> Optional[str]:
    """Why the PIN must not be tried on a card with this PIN status, or None."""
    left = pin.get("attempts_left")
    if pin.get("blocked"):
        return ("the SIM PIN is blocked: only its PUK (from the operator) unlocks it, and "
                "this tool never sends a PUK")
    if pin.get("needed") is False:
        return "the SIM PIN is off, so nothing needs it: run sim-report instead"
    if not pin.get("needed") or not isinstance(left, int):
        return ("the card did not say whether its PIN is on or how many attempts are left, "
                "so the PIN is not tried")
    if left <= 1:
        return ("the SIM has only %s left: a wrong PIN would block it until its PUK is "
                "entered, so the PIN is not tried here" % _attempts(left))
    return None


def _pin_state(con: Any, opts: Options) -> Union[str, Dict[str, Any]]:
    """Open the link, read the card number and the PIN status, close the link.

    Returns why the PIN must not be tried, or ``{"identity", "attempts_left"}``.
    """
    with SimLink.open(con, opts["clock_hz"], atr_wait_s=float(opts["wait_s"])) as link:
        reader, _, pin, _ = _route(link)
    why = _pin_refusal(pin)
    if why:
        return why
    iccid, _ = _decoded(reader, "EF_ICCID", dec.decode_iccid)
    number = iccid["iccid"] if iccid else "unknown"
    return {"identity": "ICCID %s, %s left" % (number, _attempts(pin["attempts_left"])),
            "attempts_left": pin["attempts_left"]}


def _pin_check(con: Any, opts: Options) -> Dict[str, Any]:
    """The clock, the PIN's form, then the card: ICCID and attempts left are the identity.

    Never names the PIN. Refuses (no VERIFY with a PIN is sent) when the PIN
    is not 4 to 8 digits, when the PIN is off or blocked, or when one attempt
    or fewer is left."""
    clock = check_clock(con, opts)
    if not clock.get("ok"):
        return clock
    pin = opts.get("pin")
    if not isinstance(pin, str) or not _PIN_RE.fullmatch(pin):
        return {"ok": False, "error": "the SIM PIN must be 4 to 8 digits (0-9), given as text",
                "hint": "plan again with the PIN; " + NOTHING_SENT}
    state = _pin_state(con, opts)
    if isinstance(state, str):
        return {"ok": False, "error": state, "hint": NOTHING_SENT}
    return {"ok": True, "identity": state["identity"],
            "attempts_left": state["attempts_left"]}


def _pin_prepare(con: Any, opts: Options) -> Dict[str, Any]:
    """Read a SIM card with its PIN: the PIN is tried once, only after its own yes."""
    state = _pin_state(con, opts)
    if isinstance(state, str):  # the check passed a moment ago, so this is unexpected
        raise TerminalError(state)
    left = state["attempts_left"]
    summary = ("Try the SIM PIN once. The SIM has %d attempts left; a wrong PIN leaves %d, "
               "and at 0 the SIM is blocked until its PUK is entered." % (left, left - 1))
    return {"chip": "SIM card", "operation": "verify PIN", "start": 0, "length": 0,
            "summary": summary, "backup": None}


def _pin_commit(con: Any, opts: Options, prepared: Dict[str, Any]) -> Dict[str, Any]:
    """Present the PIN exactly once, then read the report. Never retried.

    The PIN status is read again on this link first: a card that no longer
    allows a try gets no VERIFY. A wrong PIN is not a commit: the result says
    how many attempts are left now, and the fields that need the PIN stay
    locked."""
    link = SimLink.open(con, opts["clock_hz"], atr_wait_s=float(opts["wait_s"]))
    # The context manager closes the link (async print off, clock off) on every path.
    with link:
        _, _, pin, _ = _route(link)
        why = _pin_refusal(pin)
        if why:
            return {"error": why, "hint": NOTHING_SENT}
        tried = link.verify_pin_once(opts["pin"])
        report, after = _build(link)
    left = tried["attempts_left"]
    if left is None and not tried["verified"]:
        left = after.get("attempts_left")
    out = {"verified": tried["verified"], "attempts_left": left,
           "blocked": bool(tried["blocked"] or after.get("blocked"))}  # type: Dict[str, Any]
    if tried["verified"]:
        report["summary"]["pin"] = "on, verified"
    elif out["blocked"]:
        out["hint"] = ("the SIM refused the PIN and is now blocked: only its PUK (from the "
                       "operator) unlocks it; the fields that need the PIN stay locked")
    else:
        count = _attempts(left) if isinstance(left, int) else "an unknown number of attempts"
        out["hint"] = ("the SIM refused the PIN: it has %s left now. Nothing was retried; "
                       "the fields that need the PIN stay locked" % count)
    out.update(report)
    return out


register(Recipe(
    name="sim-report-pin",
    title="SIM card: the business summary with the SIM PIN (tried once, after its own yes)",
    words=("sim", "sim card", "sim pin", "pin", "usim", "locked", "report"),
    bus="uart", transport="terminal", terminal_mode="hduart", terminal_flags=TERMINAL_FLAGS,
    default_mv=3000, min_mv=1800, max_mv=5000, milliamps=100, pullups=True,
    target_powered_ok=False, options=dict(OPTIONS, pin=None), risk="destructive",
    check=_pin_check, action=_pin_prepare, commit=_pin_commit, wiring=WIRING,
    change_lines=(verify_line(GSM_CLA), verify_line(UICC_CLA)), change_hint=PIN_HINT,
    no_rerun=NO_RERUN,
    notes=("reads like sim-report, and with the SIM PIN reads the files the PIN locks; it "
           "still never reads contacts, text messages, the phone number or call records",
           "the PIN (4 to 8 digits) is tried exactly once, only after its own yes, and never "
           "retried; it is refused when the SIM has one attempt or fewer left",
           "3 V suits most SIMs; an old 5 V-only SIM needs 5000 mV"),
    source=SOURCE))
