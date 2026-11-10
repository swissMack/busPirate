import hashlib

import pytest

from buspirate.exceptions import BusPirateError
from buspirate.mcp_bp6 import memory


class Chip:
    def __init__(self, size=64, fill=0x11, ignore_writes=False):
        self.mem = bytearray([fill]) * size
        self.size = size
        self.ignore = ignore_writes
        self.calls = []

    def read(self, start, length):
        return bytes(self.mem[start:start + length])

    def write_span(self, start, image):
        self.calls.append((start, bytes(image)))
        if not self.ignore:
            self.mem[start:start + len(image)] = image


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def _file(tmp_path, data=b"\x01\x02\x03\x04", name="x.bin"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_parse_write_file(tmp_path):
    p = _file(tmp_path)
    job = memory.parse_job({"offset": 2, "file": p}, 64)
    assert (job.operation, job.offset, job.length, job.data) == ("write", 2, 4, b"\x01\x02\x03\x04")
    assert p in job.source and hashlib.sha256(job.data).hexdigest() in job.source


def test_parse_data_hex_and_erase():
    job = memory.parse_job({"data_hex": "0xde,ad be ef"}, 64)
    assert job.data == b"\xde\xad\xbe\xef" and "4 bytes" in job.source
    e = memory.parse_job({"operation": "erase", "offset": 10}, 64)
    assert (e.operation, e.length, e.data) == ("erase", 54, None)
    assert memory.parse_job({"operation": "erase", "length": 5}, 64).length == 5


def test_parse_refuses(tmp_path):
    p = _file(tmp_path)
    empty = _file(tmp_path, b"", "e.bin")
    bad = [
        {"file": p, "data_hex": "00"},
        {},
        {"operation": "erase", "data_hex": "00"},
        {"operation": "erase", "file": p},
        {"file": str(tmp_path / "missing.bin")},
        {"file": str(tmp_path)},
        {"file": empty},
        {"data_hex": "00", "offset": 64},
        {"data_hex": "00", "offset": -1},
        {"data_hex": "00" * 5, "offset": 60},
        {"data_hex": "00", "offset": True},
        {"data_hex": "00", "operation": "format"},
        {"data_hex": "zz"},
        {"operation": "erase", "offset": 60, "length": 10},
    ]
    for opts in bad:
        with pytest.raises(ValueError):
            memory.parse_job(opts, 64)


def test_prepare_saves_backup(tmp_path):
    chip = Chip()
    job = memory.parse_job({"offset": 4, "data_hex": "aabb"}, 64)
    prep = memory.prepare(job, chip.read, "24C02", "eeprom", True)
    assert prep["backup"]["bytes"] == 2
    assert open(prep["backup"]["path"], "rb").read() == b"\x11\x11"
    assert prep["backup"]["path"] in prep["summary"]
    assert prep["chip"] == "24C02" and prep["operation"] == "write"
    assert (prep["start"], prep["length"]) == (4, 2)
    assert (prep["span_start"], prep["span_length"]) == (4, 2)
    assert prep["_sha"] == hashlib.sha256(b"\x11\x11").hexdigest()
    assert "0x000004" in prep["summary"]


def test_prepare_declined():
    chip = Chip()
    job = memory.parse_job({"data_hex": "aa"}, 64)
    prep = memory.prepare(job, chip.read, "24C02", "eeprom", False)
    assert prep["backup"] is None and "declined" in prep["summary"]


def test_commit_writes_and_verifies():
    chip = Chip()
    job = memory.parse_job({"offset": 4, "data_hex": "aabb"}, 64)
    prep = memory.prepare(job, chip.read, "c", "l", False)
    r = memory.commit(prep, chip.read, chip.write_span)
    assert r["verified"] is True and r["written"] == 2 and r["mismatches"] == 0
    assert r["first_bad"] is None and "hint" not in r
    assert chip.mem[4:6] == b"\xaa\xbb"


def test_commit_erase_writes_ff():
    chip = Chip()
    job = memory.parse_job({"operation": "erase", "offset": 60}, 64)
    prep = memory.prepare(job, chip.read, "c", "l", False)
    assert memory.commit(prep, chip.read, chip.write_span)["verified"] is True
    assert chip.mem[60:] == b"\xff" * 4 and chip.mem[:60] == b"\x11" * 60


def test_commit_span_keeps_neighbours():
    chip = Chip()
    chip.mem[:] = bytes(range(64))
    job = memory.parse_job({"offset": 4, "data_hex": "aabbccdd"}, 64)
    prep = memory.prepare(job, chip.read, "c", "l", False, span=(0, 16))
    r = memory.commit(prep, chip.read, chip.write_span)
    start, image = chip.calls[0]
    assert start == 0 and len(image) == 16
    assert image[:4] == bytes(range(4)) and image[8:] == bytes(range(8, 16))
    assert image[4:8] == b"\xaa\xbb\xcc\xdd"
    assert r["span_start"] == 0 and r["span_length"] == 16 and r["written"] == 4


def test_commit_refuses_changed():
    chip = Chip()
    job = memory.parse_job({"offset": 4, "data_hex": "aabb"}, 64)
    prep = memory.prepare(job, chip.read, "c", "l", False)
    chip.mem[5] = 0x99
    assert memory.commit(prep, chip.read, chip.write_span) == {"error": memory.CHANGED}
    assert chip.calls == []


def test_commit_reports_unverified():
    chip = Chip(ignore_writes=True)
    job = memory.parse_job({"offset": 4, "data_hex": "aabb"}, 64)
    prep = memory.prepare(job, chip.read, "c", "l", True)
    r = memory.commit(prep, chip.read, chip.write_span)
    assert r["verified"] is False and r["first_bad"] == "0x000004" and r["mismatches"] == 2
    assert prep["backup"]["path"] in r["hint"] and "WP pin" in r["hint"]


def test_commit_unverified_without_backup_says_so():
    chip = Chip(ignore_writes=True)
    job = memory.parse_job({"data_hex": "aa"}, 64)
    prep = memory.prepare(job, chip.read, "c", "l", False)
    r = memory.commit(prep, chip.read, chip.write_span)
    assert "no backup was saved" in r["hint"]


class Boom(BusPirateError):
    pass


def test_commit_reports_write_error():
    chip = Chip()
    job = memory.parse_job({"offset": 4, "data_hex": "aabb"}, 64)
    prep = memory.prepare(job, chip.read, "c", "l", True)

    def bad(start, image):
        raise Boom("no ACK")

    r = memory.commit(prep, chip.read, bad)
    assert r["error"] == "no ACK" and r["verified"] is False
    assert r["backup"] == prep["backup"]
    assert prep["backup"]["path"] in r["hint"]


def test_prepare_refuses_span_not_covering_job():
    chip = Chip()
    job = memory.parse_job({"offset": 4, "data_hex": "aabbccdd"}, 64)
    for span in [(5, 16), (0, 6), (8, 8)]:
        with pytest.raises(ValueError):
            memory.prepare(job, chip.read, "c", "l", False, span=span)


def test_prepare_refuses_short_read():
    chip = Chip()
    job = memory.parse_job({"offset": 4, "data_hex": "aa"}, 64)
    with pytest.raises(ValueError):
        memory.prepare(job, lambda s, n: chip.read(s, n - 1), "c", "l", False)


def test_commit_short_reread_writes_nothing():
    chip = Chip()
    job = memory.parse_job({"offset": 4, "data_hex": "aabb"}, 64)
    prep = memory.prepare(job, chip.read, "c", "l", True)
    r = memory.commit(prep, lambda s, n: chip.read(s, n - 1), chip.write_span)
    assert r["verified"] is False and "nothing was written" in r["error"]
    assert prep["backup"]["path"] in r["hint"] and chip.calls == []
