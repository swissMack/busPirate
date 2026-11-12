"""Build the SIM report's country and operator tables in buspirate/devices/data/.

Run once to update; the result is committed and the app never goes online for it.

    .venv/bin/python scripts/build_sim_tables.py              # download the pinned sources, rebuild
    .venv/bin/python scripts/build_sim_tables.py --sources D  # rebuild from files already in D

Sources (all Apache License 2.0; none of the three repositories ships a NOTICE
file, checked 2026-11-12), pinned to the commits retrieved 2026-11-12:

- ``MccTable.java``, Android Open Source Project, platform/frameworks/opt/telephony
  @ 307806916047d68377ff74674f95ca499243e068, path
  src/java/com/android/internal/telephony/MccTable.java. MCC -> ISO code, with a
  comment naming the country as in ITU-T E.212.
- ``carrier_list.textpb``, Android Open Source Project,
  platform/packages/providers/TelephonyProvider
  @ bca387f553a4493c88e24455172225fd1049c91f, path
  assets/latest_carrier_id/carrier_list.textpb (carrier id version 134217771).
  Licence from the module's Android.bp (``Android-Apache-2.0``).
- ``CountryCodeToRegionCodeMap.java``, libphonenumber (github.com/google/libphonenumber)
  @ 981600cc587fb87483ad294a61daa187afc64b2c, path
  java/libphonenumber/src/com/google/i18n/phonenumbers/CountryCodeToRegionCodeMap.java.

Rules:

- Countries (``mcc_mnc.csv`` rows with an empty mnc): the MccTable comment with
  the official-form suffix in parentheses dropped ("Switzerland (Confederation
  of)" -> "Switzerland"), except the plain names in ``MCC_NAMES``.
- Operators (``mcc_mnc.csv`` rows with an mnc): from carrier_list, only
  ``carrier_attribute`` blocks that match on ``mccmnc_tuple`` alone (no SPN,
  GID, IMSI prefix, ICCID prefix, ...), i.e. the network operator rather than
  an MVNO riding on it. When several carriers match one tuple, the one without
  ``parent_canonical_id`` wins, then the lowest ``canonical_id``. Tuples keep
  their MNC length (5 digits = 2-digit MNC, 6 = 3-digit), so "22801" and
  "228001" stay different networks.
- Calling codes (``calling_codes.csv``, for the ICCID's country): every region
  libphonenumber lists for the code, named by ``ISO_NAMES`` or else via MccTable's ISO
  codes and joined with "or"; code 1 is
  ``CALLING_CODE_NAMES``; non-geographic codes (region "001") are
  "International (non-geographic)".
"""

from __future__ import annotations

import argparse
import base64
import csv
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

OUT = Path(__file__).resolve().parent.parent / "buspirate" / "devices" / "data"
RETRIEVED = "2026-11-12"
SCRIPT = "scripts/build_sim_tables.py"

AOSP = "https://android.googlesource.com"
MCC_URL = (AOSP + "/platform/frameworks/opt/telephony/+/307806916047d68377ff74674f95ca499243e068/"
           "src/java/com/android/internal/telephony/MccTable.java")
CARRIER_URL = (AOSP + "/platform/packages/providers/TelephonyProvider/+/bca387f553a4493c88e24455172225fd1049c91f/"
               "assets/latest_carrier_id/carrier_list.textpb")
CODES_URL = ("https://raw.githubusercontent.com/google/libphonenumber/981600cc587fb87483ad294a61daa187afc64b2c/"
             "java/libphonenumber/src/com/google/i18n/phonenumbers/CountryCodeToRegionCodeMap.java")
SOURCES = {"MccTable.java": MCC_URL, "carrier_list.textpb": CARRIER_URL,
           "CountryCodeToRegionCodeMap.java": CODES_URL}

#: Plain names where the E.212 name, even shortened, is not what people say.
MCC_NAMES = {
    "234": "United Kingdom", "235": "United Kingdom", "250": "Russia", "450": "South Korea",
    "467": "North Korea", "289": "Abkhazia", "294": "North Macedonia", "653": "Eswatini",
    "457": "Laos", "629": "Congo", "630": "Democratic Republic of the Congo",
}
#: ISO 3166 names for regions that share a calling code, used before MccTable's name
#: (Réunion's MCC 647 also covers Mayotte, so its MCC name does not fit +262).
ISO_NAMES = {
    "RE": "Réunion",
    "GG": "Guernsey", "IM": "Isle of Man", "JE": "Jersey", "SJ": "Svalbard and Jan Mayen",
    "CC": "Cocos (Keeling) Islands", "CX": "Christmas Island", "EH": "Western Sahara",
    "YT": "Mayotte", "AX": "Åland Islands", "BL": "Saint Barthélemy",
    "MF": "Saint Martin", "BQ": "Caribbean Netherlands", "SX": "Sint Maarten",
}
CALLING_CODE_NAMES = {"1": "North America (NANP: USA, Canada and the Caribbean)"}

_MCC_ENTRY = re.compile(r'MccEntry\((\d+),\s*"(\w*)",\s*(\d)\)\);\s*//\s*(.*)')


def download(directory: Path) -> None:
    for name, url in SOURCES.items():
        if url.startswith(AOSP):
            data = base64.b64decode(urllib.request.urlopen(url + "?format=TEXT", timeout=120).read())
        else:
            data = urllib.request.urlopen(url, timeout=120).read()
        (directory / name).write_bytes(data)


def countries(mcc_table: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """MCC -> country, and ISO code -> country (first MCC wins)."""
    by_mcc = {}  # type: Dict[str, str]
    by_iso = {}  # type: Dict[str, str]
    for mcc, iso, _digits, comment in _MCC_ENTRY.findall(mcc_table):
        name = MCC_NAMES.get(mcc) or re.sub(r"\s*\(.*$", "", comment).strip()
        by_mcc[mcc] = name
        by_iso.setdefault(iso.upper(), name)
    return by_mcc, by_iso


def operators(carrier_list: str) -> List[Tuple[str, str, str]]:
    candidates = {}  # type: Dict[str, List[Tuple[bool, int, str]]]
    for block in re.split(r"^carrier_id \{", carrier_list, flags=re.M)[1:]:
        cid = int(re.search(r"canonical_id: (\d+)", block).group(1))
        name = re.search(r'carrier_name: "(.*)"', block)
        if not name:
            continue
        has_parent = "parent_canonical_id" in block
        for attr in re.findall(r"carrier_attribute \{(.*?)\n  \}", block, flags=re.S):
            if set(re.findall(r"^\s*(\w+):", attr, flags=re.M)) != {"mccmnc_tuple"}:
                continue
            for tup in re.findall(r'mccmnc_tuple: "(\d+)"', attr):
                candidates.setdefault(tup, []).append((has_parent, cid, name.group(1).strip()))
    return [(tup[:3], tup[3:], sorted(found)[0][2])
            for tup, found in sorted(candidates.items()) if len(tup) in (5, 6)]


def calling_codes(code_map: str, by_iso: Dict[str, str]) -> List[Tuple[str, str]]:
    rows = []
    for block in re.split(r"listWithRegionCode = new", code_map)[1:]:
        regions = re.findall(r'listWithRegionCode\.add\("(\w+)"\)', block)
        code = re.search(r"countryCodeToRegionCodeMap\.put\((\d+), listWithRegionCode\)", block).group(1)
        if code in CALLING_CODE_NAMES:
            name = CALLING_CODE_NAMES[code]
        elif regions == ["001"]:
            name = "International (non-geographic)"
        else:
            names = []  # type: List[str]
            for region in regions:
                found = ISO_NAMES.get(region) or by_iso.get(region)
                if found and found not in names:
                    names.append(found)
            if not names:
                continue
            name = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]
        rows.append((code, name))
    return sorted(rows, key=lambda row: int(row[0]))


def build(src: Path, out: Path) -> None:
    by_mcc, by_iso = countries((src / "MccTable.java").read_text(encoding="utf-8"))
    ops = operators((src / "carrier_list.textpb").read_text(encoding="utf-8"))
    codes = calling_codes((src / "CountryCodeToRegionCodeMap.java").read_text(encoding="utf-8"), by_iso)
    with open(out / "mcc_mnc.csv", "w", encoding="utf-8", newline="") as f:
        f.write("# Built by %s. Countries: MCC to country from Android Open Source Project MccTable.java (%s, "
                "names as in ITU-T E.212, official-form suffixes dropped); operators: MCC+MNC to network operator "
                "from AOSP carrier_list.textpb (%s, version 134217771, entries matching on MCC+MNC alone); "
                "both Apache License 2.0, Copyright The Android Open Source Project; retrieved %s.\n"
                % (SCRIPT, MCC_URL, CARRIER_URL, RETRIEVED))
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("mcc", "mnc", "name"))
        writer.writerows((mcc, "", name) for mcc, name in sorted(by_mcc.items()))
        writer.writerows(ops)
    with open(out / "calling_codes.csv", "w", encoding="utf-8", newline="") as f:
        f.write("# Built by %s. Country calling codes (ITU-T E.164) to country, for the ICCID: regions per code "
                "from libphonenumber CountryCodeToRegionCodeMap.java (%s, Apache License 2.0, Copyright The "
                "Libphonenumber Authors), named via AOSP MccTable.java (Apache License 2.0); retrieved %s.\n"
                % (SCRIPT, CODES_URL, RETRIEVED))
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("code", "country"))
        writer.writerows(codes)
    print("%d countries, %d operators, %d calling codes -> %s" % (len(by_mcc), len(ops), len(codes), out))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sources", type=Path, help="directory holding the three source files (default: download)")
    parser.add_argument("--out", type=Path, default=OUT, help="output directory (default: %(default)s)")
    args = parser.parse_args(argv)
    if args.sources:
        build(args.sources, args.out)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            download(Path(tmp))
            build(Path(tmp), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
