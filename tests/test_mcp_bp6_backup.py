import datetime
import hashlib

from buspirate.mcp_bp6 import backup

T = datetime.datetime(2026, 11, 10, 12, 0, 5)


def test_save_writes_named_file(tmp_path):
    r = backup.save(b"hello", "eeprom", folder=tmp_path, now=T)
    p = tmp_path / "eeprom-20261110-120005.bin"
    assert r == {"path": str(p), "bytes": 5, "sha256": hashlib.sha256(b"hello").hexdigest()}
    assert p.read_bytes() == b"hello"


def test_twice_in_one_second_never_overwrites(tmp_path):
    a = backup.save(b"one", "x", folder=tmp_path, now=T)
    b = backup.save(b"two", "x", folder=tmp_path, now=T)
    c = backup.save(b"three", "x", folder=tmp_path, now=T)
    assert a["path"] != b["path"] != c["path"]
    assert b["path"].endswith("x-20261110-120005-2.bin")
    assert c["path"].endswith("x-20261110-120005-3.bin")
    assert open(a["path"], "rb").read() == b"one"


def test_creates_folder_and_default_is_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    r = backup.save(b"z", "w", now=T)
    assert r["path"].startswith(str(tmp_path / "BusPirate" / "backups"))


def test_what_cannot_escape_the_folder(tmp_path):
    folder = tmp_path / "out"
    r = backup.save(b"x", "../x/y", folder=folder, now=T)
    from pathlib import Path
    p = Path(r["path"])
    assert p.parent == folder and p.read_bytes() == b"x"
    assert "/" not in p.name and not (tmp_path / "x").exists()
