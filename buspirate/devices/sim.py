"""SIM card files: what the bytes read from a SIM or USIM say, in plain words.

Pure decoders, no I/O: :mod:`buspirate.bp6.sim` reads the files, these turn
them into named fields. Codings follow 3GPP TS 31.102 (USIM), TS 51.011 (GSM
SIM), TS 24.008 / TS 24.301 (PLMN, LAI, TAI), ITU-T E.118 (ICCID) and ETSI
TS 101 220 (application identifiers).

Country and operator names come from tables bundled in ``data/`` (see the
first line of each CSV for its source, licence and retrieval date):
``mcc_mnc.csv`` (mobile country code to country, MCC+MNC to operator) and
``calling_codes.csv`` (country calling code to country, for the ICCID).
"""

from __future__ import annotations

import csv
import io
import pkgutil
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEVICES: list = []

# -- bundled tables ----------------------------------------------------------

_TABLES = {}  # type: Dict[str, Any]


def _rows(name: str) -> List[List[str]]:
    data = pkgutil.get_data(__name__.rpartition(".")[0], "data/" + name)
    if data is None:  # pragma: no cover - a loader without get_data support
        raise FileNotFoundError(name)
    lines = [line for line in data.decode("utf-8").splitlines() if not line.startswith("#")]
    return list(csv.reader(io.StringIO("\n".join(lines))))[1:]  # drop the header row


def _mcc_tables() -> Tuple[Dict[str, str], Dict[Tuple[str, str], str]]:
    if "mcc" not in _TABLES:
        countries = {}  # type: Dict[str, str]
        operators = {}  # type: Dict[Tuple[str, str], str]
        for mcc, mnc, name in _rows("mcc_mnc.csv"):
            if mnc:
                operators[(mcc, mnc)] = name
            else:
                countries[mcc] = name
        _TABLES["mcc"] = (countries, operators)
    return _TABLES["mcc"]


def _calling_codes() -> Dict[str, str]:
    if "cc" not in _TABLES:
        _TABLES["cc"] = {code: name for code, name in _rows("calling_codes.csv")}
    return _TABLES["cc"]


def country(mcc: str) -> Optional[str]:
    """The country a mobile country code (3 digits, a string) belongs to, or None."""
    return _mcc_tables()[0].get(mcc)


def operator(mcc: str, mnc: str) -> Optional[str]:
    """The network operator for an MCC and MNC (2 or 3 digits, as on the card), or None.

    ``"01"`` and ``"001"`` are different networks, so the MNC must have the
    length the card says (``mnc_digits``); a wrong length finds nothing rather
    than another operator's name.
    """
    return _mcc_tables()[1].get((mcc, mnc))


# -- digits ------------------------------------------------------------------

def _swapped_digits(data: bytes) -> str:
    """BCD with the low nibble first, stopping at the first F (padding)."""
    out = []
    for byte in data:
        for nibble in (byte & 0x0F, byte >> 4):
            if nibble == 0x0F:
                return "".join(out)
            if nibble > 9:
                raise ValueError("not a decimal digit: 0x%X" % nibble)
            out.append(str(nibble))
    return "".join(out)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# -- ICCID (EF_ICCID, 2FE2) --------------------------------------------------

def decode_iccid(b: bytes) -> Dict[str, Any]:
    """The card's serial number (ICCID, ITU-T E.118): 19 or 20 digits, the last a Luhn check digit.

    ``industry`` is the major industry identifier ("89" is telecoms);
    ``country`` comes from the country calling code after it (1 to 3 digits),
    ``issuer_id`` is the two digits after that (the issuer field is 1 to 4
    digits long and its length is set per country; two is the most common).
    Raises ValueError on an empty or non-decimal number.
    """
    digits = _swapped_digits(bytes(b))
    if not digits:
        raise ValueError("the ICCID is empty")
    result = {"iccid": digits, "luhn_ok": _luhn_ok(digits), "industry": None,
              "country": None, "issuer_id": None}  # type: Dict[str, Any]
    if digits.startswith("89"):
        result["industry"] = "Telecommunications"
        codes = _calling_codes()
        rest = digits[2:]
        for n in (1, 2, 3):
            if rest[:n] in codes:
                result["country"] = codes[rest[:n]]
                result["issuer_id"] = rest[n:n + 2] or None
                break
    else:
        result["industry"] = "Unknown (starts %s, not a telecom card)" % digits[:2]
    return result


# -- IMSI (EF_IMSI, 6F07) and EF_AD (6FAD) ------------------------------------

def mnc_digits(ef_ad: bytes) -> int:
    """How many digits the MNC in the IMSI has: EF_AD byte 4 (b4..b1), 2 when absent or invalid."""
    ef_ad = bytes(ef_ad)
    if len(ef_ad) < 4:
        return 2
    value = ef_ad[3] & 0x0F
    return value if value in (2, 3) else 2


def mnc_length_known(ef_ad: bytes) -> bool:
    """Whether EF_AD says how long the MNC is (byte 4 present, b4..b1 2 or 3)."""
    ef_ad = bytes(ef_ad)
    return len(ef_ad) >= 4 and ef_ad[3] & 0x0F in (2, 3)


def mixed_mnc_mccs() -> frozenset:
    """The MCCs whose networks in the operator table have both 2- and 3-digit MNCs.

    For these an IMSI cannot be split into MCC and MNC without EF_AD."""
    if "mixed" not in _TABLES:
        lengths = {}  # type: Dict[str, set]
        for mcc, mnc in _mcc_tables()[1]:
            lengths.setdefault(mcc, set()).add(len(mnc))
        _TABLES["mixed"] = frozenset(m for m, n in lengths.items() if n >= {2, 3})
    return _TABLES["mixed"]


def operator_candidates(imsi: str) -> List[Tuple[str, Optional[str]]]:
    """``[(2-digit MNC, operator or None), (3-digit MNC, operator or None)]`` for an IMSI."""
    mcc = imsi[:3]
    return [(imsi[3:3 + n], operator(mcc, imsi[3:3 + n])) for n in (2, 3)]


def decode_imsi(b: bytes, mnc_digits: int) -> Dict[str, str]:
    """The subscriber identity (IMSI): MCC (3 digits), MNC (``mnc_digits``) and MSIN.

    Byte 1 is the length; the low nibble of byte 2 is the identity type and
    parity, its high nibble the first digit; the rest is swapped BCD.
    Raises ValueError on an unset (all FF) or malformed file.
    """
    b = bytes(b)
    if mnc_digits not in (2, 3):
        raise ValueError("mnc_digits must be 2 or 3")
    if len(b) < 2 or b[0] == 0xFF or b[0] == 0 or b[0] > 8 or len(b) < 1 + b[0]:
        raise ValueError("no IMSI on this card (file unset or malformed)")
    body = b[1:1 + b[0]]
    # The first digit is the high nibble of the first byte; the low nibble is type/parity.
    first = body[0] >> 4
    if first > 9:
        raise ValueError("no IMSI on this card (file unset or malformed)")
    digits = str(first) + _swapped_digits(body[1:])
    if len(digits) < 6:
        raise ValueError("the IMSI is too short: %s" % digits)
    mcc, mnc = digits[:3], digits[3:3 + mnc_digits]
    return {"imsi": digits, "mcc": mcc, "mnc": mnc, "msin": digits[3 + mnc_digits:]}


# -- text (SPN, EF_DIR labels) ------------------------------------------------

_GSM_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM_EXT = {0x0A: "\f", 0x14: "^", 0x28: "{", 0x29: "}", 0x2F: "\\", 0x3C: "[",
            0x3D: "~", 0x3E: "]", 0x40: "|", 0x65: "€"}


def _gsm_text(data: bytes) -> str:
    out = []
    escape = False
    for byte in data:
        if byte == 0xFF:
            break
        byte &= 0x7F
        if escape:
            out.append(_GSM_EXT.get(byte, " "))
            escape = False
        elif byte == 0x1B:
            escape = True
        else:
            out.append(_GSM_BASIC[byte])
    return "".join(out)


def _sim_text(data: bytes) -> str:
    """An alpha field (TS 31.101 Annex A / TS 51.011 Annex B): GSM 7-bit unpacked or one of the UCS2 forms."""
    data = bytes(data)
    if not data:
        return ""
    if data[0] == 0x80:
        chars = []
        body = data[1:]
        for i in range(0, len(body) - 1, 2):
            code = (body[i] << 8) | body[i + 1]
            if code == 0xFFFF:
                break
            chars.append(chr(code))
        return "".join(chars)
    if data[0] in (0x81, 0x82) and len(data) >= 3:
        count = data[1]
        if data[0] == 0x81:
            base, start = data[2] << 7, 3
        else:
            if len(data) < 4:
                return ""
            base, start = (data[2] << 8) | data[3], 4
        chars = []
        for byte in data[start:start + count]:
            if byte & 0x80:
                chars.append(chr(base + (byte & 0x7F)))
            else:
                chars.append(_GSM_BASIC[byte])
        return "".join(chars)
    return _gsm_text(data)


def decode_spn(b: bytes) -> Dict[str, Any]:
    """The service provider name (EF_SPN, 6F46) the phone shows.

    ``show_on_phone`` is whether the phone must show this name when roaming
    too (byte 1 b2 = 0); on the home network it is always shown.
    ``show_network_name`` is byte 1 b1: whether the phone must also show the
    network's own name at home.
    """
    b = bytes(b)
    if not b:
        return {"name": "", "show_on_phone": False, "show_network_name": False}
    condition = b[0]
    return {"name": _sim_text(b[1:]).strip(),
            "show_on_phone": not condition & 0x02,
            "show_network_name": bool(condition & 0x01)}


# -- PLMNs ---------------------------------------------------------------------

def _plmn(b: bytes) -> Optional[Tuple[str, str]]:
    """MCC and MNC from 3 bytes (TS 24.008): MCC2|MCC1, MNC3|MCC3, MNC2|MNC1; MNC3 = F means 2 digits."""
    if len(b) < 3:
        return None
    mcc1, mcc2 = b[0] & 0x0F, b[0] >> 4
    mcc3, mnc3 = b[1] & 0x0F, b[1] >> 4
    mnc1, mnc2 = b[2] & 0x0F, b[2] >> 4
    if max(mcc1, mcc2, mcc3, mnc1, mnc2) > 9 or (mnc3 > 9 and mnc3 != 0x0F):
        return None
    mcc = "%d%d%d" % (mcc1, mcc2, mcc3)
    mnc = "%d%d" % (mnc1, mnc2) + ("" if mnc3 == 0x0F else str(mnc3))
    return mcc, mnc


def _network(b: bytes) -> Optional[Dict[str, Any]]:
    plmn = _plmn(b)
    if plmn is None:
        return None
    mcc, mnc = plmn
    return {"mcc": mcc, "mnc": mnc, "operator": operator(mcc, mnc), "country": country(mcc)}


# Access technology identifier (TS 31.102 §4.2.5). Two fields are coded as
# three bits read together, not bit by bit:
#   table 4.2.5.2, byte 2 b8 b4 b3: 0xx none, 100 GSM and EC-GSM-IoT,
#     101 GSM without EC-GSM-IoT, 110 EC-GSM-IoT only, 111 GSM and EC-GSM-IoT;
#   table 4.2.5.1, byte 1 b7 b6 b5: 0xx none, 100 WB-S1 and NB-S1,
#     101 NB-S1 only, 110 WB-S1 only, 111 WB-S1 and NB-S1.
# 100 is the legacy coding (one "E-UTRAN" bit, one "GSM" bit) that almost every
# SIM stores, and 111 means the same, so both name only the general technology:
# NB-IoT comes only from 101 (NB-S1 only), EC-GSM-IoT only from 110.
_GSM = "2G (GSM)"
_EC_GSM = "2G (EC-GSM-IoT)"
_LTE = "4G (E-UTRAN)"
_NB_IOT = "4G NB-IoT (E-UTRAN NB-S1)"
_GSM_FIELD = {0b100: (_GSM,), 0b101: (_GSM,), 0b110: (_EC_GSM,), 0b111: (_GSM,)}
_EUTRAN_FIELD = {0b100: (_LTE,), 0b101: (_NB_IOT,), 0b110: (_LTE,), 0b111: (_LTE,)}
#: Byte 2 b2 b1 are RFU: set, the identifier is not a coding this table knows.
_ACT_RFU = 0x03
#: Report order: oldest technology first.
_ACT_ORDER = (_GSM, "2G (GSM COMPACT)", _EC_GSM, "3G (UTRAN)", "3G (cdma2000 HRPD)", "3G (cdma2000 1xRTT)",
              _LTE, _NB_IOT, "5G (NG-RAN)", "5G by satellite (NG-RAN)", "4G by satellite (E-UTRAN WB-S1)",
              "4G by satellite (E-UTRAN NB-S1)")
#: Bits that stand alone: (byte index, mask, name).
_ACT_SINGLE = (
    (1, 0x40, "2G (GSM COMPACT)"),
    (0, 0x80, "3G (UTRAN)"),
    (1, 0x20, "3G (cdma2000 HRPD)"),
    (1, 0x10, "3G (cdma2000 1xRTT)"),
    (0, 0x08, "5G (NG-RAN)"),
    (0, 0x04, "5G by satellite (NG-RAN)"),
    (0, 0x02, "4G by satellite (E-UTRAN WB-S1)"),
    (0, 0x01, "4G by satellite (E-UTRAN NB-S1)"),
)


def _technologies(act: bytes) -> List[str]:
    """The technologies an access technology identifier selects; none when it
    is all ones in either byte (filler) or has a reserved (RFU) bit set:
    such a field states nothing, so nothing is claimed from it."""
    if len(act) < 2 or 0xFF in act[:2] or act[1] & _ACT_RFU:
        return []
    found = {name for index, mask, name in _ACT_SINGLE if act[index] & mask}
    gsm = (act[1] >> 7 & 1) << 2 | (act[1] >> 3 & 1) << 1 | (act[1] >> 2 & 1)  # b8 b4 b3
    eutran = act[0] >> 4 & 0x07  # b7 b6 b5
    found.update(_GSM_FIELD.get(gsm, ()))
    found.update(_EUTRAN_FIELD.get(eutran, ()))
    return [name for name in _ACT_ORDER if name in found]


def decode_plmn_list(b: bytes, with_act: bool) -> List[Dict[str, Any]]:
    """A list of networks: EF_PLMNsel / EF_FPLMN (3 bytes each) or the "with access technology" files (5 bytes each).

    Empty entries (FF FF FF) are skipped. ``technologies`` lists the radio
    technologies an entry selects, oldest first; it is empty for lists
    without access technology.
    """
    b = bytes(b)
    size = 5 if with_act else 3
    result = []
    for i in range(0, len(b) - size + 1, size):
        entry = b[i:i + size]
        network = _network(entry[:3])
        if network is None:
            continue
        network["technologies"] = _technologies(entry[3:5]) if with_act else []
        result.append(network)
    return result


# -- service tables ------------------------------------------------------------

#: USIM service table (EF_UST, 6F38), TS 31.102 §4.2.8, checked against v17.10.0.
UST_SERVICES = {
    1: "Local phone book", 2: "Fixed dialling numbers", 3: "Extension 2", 4: "Service dialling numbers",
    5: "Extension 3", 6: "Barred dialling numbers", 7: "Extension 4", 8: "Outgoing call log",
    9: "Incoming call log", 10: "Text message (SMS) storage", 11: "Text message delivery reports",
    12: "Text message settings", 13: "Advice of charge", 14: "Capability configuration parameters 2",
    15: "Cell broadcast message filter", 16: "Cell broadcast message ranges", 17: "Group identifier level 1",
    18: "Group identifier level 2", 19: "Service provider name", 20: "User preferred networks (with radio type)",
    21: "Own phone number (MSISDN)", 22: "Images", 23: "Localised service areas (SoLSA)",
    24: "Priority calls (eMLPP)", 25: "Automatic answer for priority calls", 26: "Reserved",
    27: "GSM (2G) access", 28: "Data download via text message (SMS-PP)",
    29: "Data download via cell broadcast", 30: "Call control by the SIM",
    31: "Outgoing text message control by the SIM", 32: "SIM can run AT commands", 33: "Always set",
    34: "Enabled services table", 35: "Access point name (APN) control list",
    36: "Depersonalisation control keys", 37: "Co-operative network list", 38: "GSM security context",
    39: "CPBCCH information", 40: "Investigation scan", 41: "MExE",
    42: "Operator preferred networks (with radio type)", 43: "Home network selector (with radio type)",
    44: "Extension 5", 45: "Network name", 46: "Operator network list", 47: "Voicemail number",
    48: "Message waiting indication", 49: "Call forwarding indication", 50: "Reserved",
    51: "Service provider display information", 52: "Picture messages (MMS)", 53: "Extension 8",
    54: "Call control on data (GPRS) by the SIM", 55: "Picture message (MMS) settings",
    56: "Network alerting indication", 57: "Group call list (VGCS)", 58: "Broadcast call list (VBS)",
    59: "Pseudonym", 60: "User preferred networks for I-WLAN", 61: "Operator preferred networks for I-WLAN",
    62: "User WLAN list (WSID)", 63: "Operator WLAN list (WSID)", 64: "Group call security (VGCS)",
    65: "Broadcast call security (VBS)", 66: "WLAN re-authentication identity",
    67: "Picture message (MMS) storage", 68: "Generic bootstrapping (GBA)", 69: "Mobile TV security (MBMS)",
    70: "Data download via USSD", 71: "Equivalent home networks",
    72: "Additional terminal profile after activation", 73: "Equivalent home network display",
    74: "Last registered network selection", 75: "Mobile TV smart card profile (OMA BCAST)",
    76: "GBA local key establishment", 77: "Terminal applications", 78: "Service provider name icon",
    79: "Network name icon", 80: "SIM IP connection settings", 81: "Home I-WLAN identifier list",
    82: "I-WLAN equivalent home network display", 83: "I-WLAN home network priority",
    84: "I-WLAN last registered network", 85: "EPS (4G) mobility information",
    86: "Allowed closed subscriber groups (CSG)", 87: "Call control on 4G data connections by the SIM",
    88: "Home network direct access", 89: "Emergency call data (eCall)",
    90: "Operator closed subscriber groups (CSG)", 91: "Text messages over IP (SMS over IMS)",
    92: "Closed subscriber group display control", 93: "Communication control for IMS by the SIM",
    94: "Extended terminal applications", 95: "SIM access to IMS (voice over LTE / Wi-Fi)",
    96: "Network (NAS) configuration by the SIM", 97: "Public warning (PWS) settings by the SIM",
    98: "Reserved", 99: "URI support by the card", 100: "Extended 4G channel numbers (EARFCN)",
    101: "Proximity services (ProSe)", 102: "SIM toolkit application pairing", 103: "Media type support",
    104: "IMS call disconnection cause", 105: "URI support for outgoing text message control",
    106: "Wi-Fi calling gateway (ePDG) settings supported", 107: "Wi-Fi calling gateway (ePDG) settings present",
    108: "Application-specific congestion control (ACDC)", 109: "Mission critical services",
    110: "Wi-Fi emergency calling gateway (ePDG) supported", 111: "Wi-Fi emergency calling gateway (ePDG) present",
    112: "Emergency call data over IMS (eCall)", 113: "URI support for data download via text message",
    114: "From preferred", 115: "IMS configuration data", 116: "TV configuration",
    117: "Mobile data off (3GPP PS Data Off)", 118: "Mobile data off service list",
    119: "Vehicle communication (V2X)", 120: "XCAP configuration data",
    121: "4G channel list for IoT devices (MTC/NB-IoT)", 122: "5G mobility information",
    123: "5G security parameters", 124: "Subscriber identity privacy (SUCI)",
    125: "SUCI calculated by the SIM", 126: "Access identities (UAC)",
    127: "Steering of roaming (control plane)", 128: "Call control on 5G data sessions by the SIM",
    129: "5G operator network list", 130: "SUPI of type NSI, GLI or GCI",
    131: "Mobile data off: separate home and roaming lists", 132: "Route selection policy (URSP) by the SIM",
    133: "5G security parameters (extended)", 134: "MuD and MiD configuration data",
    135: "Trusted non-3GPP access (e.g. Wi-Fi) by the SIM", 136: "Several 5G security contexts",
    137: "Pre-configured closed access groups (CAG)", 138: "Steering of roaming information (SOR-CMCI)",
    139: "5G proximity services (5G ProSe)", 140: "Disaster roaming information",
    141: "Pre-configured extended sleep (eDRX)", 142: "5G non-seamless Wi-Fi offload (NSWO)",
    143: "Public warning settings for private 5G (SNPN)", 144: "Faster home network search via 5G satellite",
}

#: GSM SIM service table (EF_SST, 6F38), TS 51.011 §10.3.7, checked against v4.15.0.
SST_SERVICES = {
    1: "PIN disable function", 2: "Phone book (abbreviated dialling numbers)", 3: "Fixed dialling numbers",
    4: "Short message storage", 5: "Advice of charge", 6: "Capability configuration parameters",
    7: "Preferred networks", 8: "Reserved", 9: "Own phone number (MSISDN)", 10: "Extension 1",
    11: "Extension 2", 12: "Text message settings", 13: "Last number dialled",
    14: "Cell broadcast message filter", 15: "Group identifier level 1", 16: "Group identifier level 2",
    17: "Service provider name", 18: "Service dialling numbers", 19: "Extension 3", 20: "Reserved",
    21: "Group call list (VGCS)", 22: "Broadcast call list (VBS)", 23: "Priority calls (eMLPP)",
    24: "Automatic answer for priority calls", 25: "Data download via cell broadcast",
    26: "Data download via text message (SMS-PP)", 27: "SIM toolkit menu", 28: "Call control by the SIM",
    29: "SIM toolkit (proactive SIM)", 30: "Cell broadcast message ranges", 31: "Barred dialling numbers",
    32: "Extension 4", 33: "Depersonalisation control keys", 34: "Co-operative network list",
    35: "Text message delivery reports", 36: "Network alerting indication",
    37: "Outgoing text message control by the SIM", 38: "Mobile data (GPRS)", 39: "Images",
    40: "Localised service areas (SoLSA)", 41: "USSD in call control", 42: "SIM can run AT commands",
    43: "User preferred networks (with radio type)", 44: "Operator preferred networks (with radio type)",
    45: "Home network selector (with radio type)", 46: "CPBCCH information", 47: "Investigation scan",
    48: "Extended capability configuration parameters", 49: "MExE", 50: "Reserved", 51: "Network name",
    52: "Operator network list", 53: "Voicemail number", 54: "Message waiting indication",
    55: "Call forwarding indication", 56: "Service provider display information",
    57: "Picture messages (MMS)", 58: "Extension 8", 59: "Picture message (MMS) settings",
}


def decode_service_table(b: bytes, kind: str) -> List[Dict[str, Any]]:
    """What the operator has switched on, one entry per service the table's bytes cover.

    ``"ust"`` (USIM, TS 31.102 §4.2.8): one bit per service, byte 1 b1 is
    service 1. ``"sst"`` (GSM SIM, TS 51.011 §10.3.7): two bits per service,
    the first "allocated", the second "activated"; ``enabled`` needs both.
    """
    b = bytes(b)
    if kind == "ust":
        names, per_byte = UST_SERVICES, 8
    elif kind == "sst":
        names, per_byte = SST_SERVICES, 4
    else:
        raise ValueError("kind must be 'ust' or 'sst', not %r" % (kind,))
    result = []
    for number in range(1, len(b) * per_byte + 1):
        index = number - 1
        byte = b[index // per_byte]
        if per_byte == 8:
            enabled = bool(byte >> (index % 8) & 1)
        else:
            bits = byte >> (2 * (index % 4)) & 0x03
            enabled = bits == 0x03
        name = names.get(number, "Service %d (not in the table)" % number)
        result.append({"number": number, "name": name, "enabled": enabled})
    return result


# -- last location -------------------------------------------------------------

_LU_STATUS = {0: "updated", 1: "not updated", 2: "network not allowed", 3: "area not allowed"}
_EPS_STATUS = {0: "updated", 1: "not updated", 2: "roaming not allowed"}


def _status(byte: int, table: Dict[int, str]) -> str:
    return table.get(byte & 0x07, "reserved")


NO_VALID_AREA = "no valid area"
#: Reserved area codes: LAC 0000 and FFFE (TS 24.008 §10.5.1.3, FFFE = deleted),
#: TAC 0000 and FFFE (TS 23.003 §19.4.2.3).
_RESERVED_AREAS = (0x0000, 0xFFFE)


def _area(network: Optional[Dict[str, Any]], b: bytes) -> Any:
    """The area code as a number, or ``NO_VALID_AREA`` when there is no network or the code is reserved."""
    if network is None or len(b) < 2:
        return NO_VALID_AREA
    code = (b[0] << 8) | b[1]
    return NO_VALID_AREA if code in _RESERVED_AREAS else code


def decode_loci(b: bytes) -> Dict[str, Any]:
    """Last network for calls (EF_LOCI, 6F7E): TMSI 4, LAI 5 (PLMN + area code), RFU, update status."""
    b = bytes(b)
    if len(b) < 11:
        raise ValueError("EF_LOCI is 11 bytes, got %d" % len(b))
    network = _network(b[4:7])
    return {"network": network, "area_code": _area(network, b[7:9]),
            "technology": "2G/3G voice (circuit switched)", "status": _status(b[10], _LU_STATUS)}


def decode_psloci(b: bytes) -> Dict[str, Any]:
    """Last network for data (EF_PSLOCI, 6F73): P-TMSI 4, signature 3, RAI 6 (LAI + RAC), update status."""
    b = bytes(b)
    if len(b) < 14:
        raise ValueError("EF_PSLOCI is 14 bytes, got %d" % len(b))
    network = _network(b[7:10])
    return {"network": network, "area_code": _area(network, b[10:12]),
            "routing_area": b[12] if network is not None else None,
            "technology": "2G/3G data (packet switched)", "status": _status(b[13], _LU_STATUS)}


def decode_epsloci(b: bytes) -> Dict[str, Any]:
    """Last 4G network (EF_EPSLOCI, 6FE3): GUTI 12, last visited TAI 5 (PLMN + tracking area code), status."""
    b = bytes(b)
    if len(b) < 18:
        raise ValueError("EF_EPSLOCI is 18 bytes, got %d" % len(b))
    network = _network(b[12:15])
    return {"network": network, "area_code": _area(network, b[15:17]),
            "technology": "4G (LTE)", "status": _status(b[17], _EPS_STATUS)}


# -- access classes and applications ---------------------------------------------

def decode_acc(b: bytes) -> List[int]:
    """Access control classes (EF_ACC, 6F78): byte 1 b8..b1 = classes 15..8, byte 2 = 7..0."""
    b = bytes(b)
    if len(b) < 2:
        raise ValueError("EF_ACC is 2 bytes, got %d" % len(b))
    value = (b[0] << 8) | b[1]
    return [n for n in range(16) if value >> n & 1 and n != 10]


# ETSI TS 101 220 Annex E: registered application provider ID + application code.
_APPLICATIONS = {
    ("A000000087", "1001"): "3GPP UICC",
    ("A000000087", "1002"): "USIM (3G/4G/5G subscriber identity)",
    ("A000000087", "1003"): "USIM toolkit",
    ("A000000087", "1004"): "ISIM (IMS, voice over LTE / Wi-Fi)",
    ("A000000087", "1005"): "(U)SIM API",
    ("A000000087", "1006"): "ISIM API",
    ("A000000087", "1007"): "3GPP contact manager",
    ("A000000087", "1008"): "USIM-INI (relay node set-up)",
    ("A000000087", "1009"): "USIM-RN (relay node)",
    ("A000000343", "1002"): "CSIM (CDMA subscriber identity)",
}


def _tlv(data: bytes) -> List[Tuple[int, bytes]]:
    out = []
    i = 0
    while i + 1 < len(data):
        tag, length = data[i], data[i + 1]
        if tag in (0x00, 0xFF):
            break
        out.append((tag, data[i + 2:i + 2 + length]))
        i += 2 + length
    return out


def decode_dir(records: Sequence[bytes]) -> List[Dict[str, str]]:
    """The applications on the card (EF_DIR, 2F00 records): ``aid`` in hex, ``application`` named.

    Each record is an application template (tag 61) holding the AID (4F) and
    an optional label (50), which is added as ``label``. Empty records are skipped.
    """
    result = []
    for record in records:
        for tag, value in _tlv(bytes(record)):
            if tag != 0x61:
                continue
            fields = dict(_tlv(value))
            aid = fields.get(0x4F)
            if not aid:
                continue
            hexaid = aid.hex().upper()
            entry = {"aid": hexaid,
                     "application": _APPLICATIONS.get((hexaid[:10], hexaid[10:14]), "Unknown application")}
            if 0x50 in fields:
                entry["label"] = _sim_text(fields[0x50])
            result.append(entry)
    return result
