import pytest

from buspirate.mcp import knowledge
from buspirate.mcp.knowledge import read, search, topics


def test_topics_listed():
    names = {t["topic"] for t in topics()}
    assert {"boards", "power", "wiring", "i2c", "spi", "uart", "onewire", "esp", "avr", "pic", "errors"} <= names


def test_topic_title_is_the_first_heading():
    for t in topics():
        assert t["title"] and not t["title"].startswith("#"), t
        assert ("# " + t["title"]) in read(t["topic"]).splitlines()[0]


def test_every_note_cites_sources():
    for t in topics():
        assert "Sources:" in read(t["topic"]), t


def test_notes_stay_short():
    for t in topics():
        assert len(read(t["topic"]).splitlines()) < 150, t


def test_search_finds_strapping_pin():
    hits = search("ESP32-C3 GPIO9 download mode")
    assert hits and hits[0]["source"] == "notes/esp.md"


def test_search_reaches_bundled_manual():
    assert any(h["source"].startswith("docs/official/") for h in search("binmode legacy flashrom"))


def test_search_hit_shape_and_limit():
    hits = search("pull-up", limit=3)
    assert 0 < len(hits) <= 3
    for h in hits:
        assert set(h) == {"source", "heading", "excerpt"}


def test_search_notes_rank_first_on_equal_scores():
    hits = search("WP HOLD")
    assert hits and hits[0]["source"].startswith("notes/")


def test_search_without_docs_uses_notes_only(monkeypatch):
    monkeypatch.setattr(knowledge, "_docs_root", lambda: None)
    hits = search("binmode legacy flashrom")
    assert hits and all(h["source"].startswith("notes/") for h in hits)


def test_search_of_nothing_is_empty():
    assert search("") == []
    assert search("zzqqxx") == []


def test_common_words_do_not_count():
    assert search("how do I the") == []


def test_unknown_topic():
    with pytest.raises(KeyError, match="boards"):
        read("nope")


def test_notes_ship_in_the_wheel():
    from pathlib import Path
    pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    assert '"buspirate.mcp" = ["notes/*.md"]' in pyproject


def test_pic_note_powers_low_voltage_parts_from_3v3_only():
    note = read("pic")
    vdd = [ln for ln in note.splitlines() if "VDD" in ln and "|" in ln]
    assert vdd and all("+3.3V" in ln for ln in vdd)
    for line in note.splitlines():
        if "+5V" in line and "VDD" in line:
            assert "never" in line or "not" in line, line
    assert "never connect the orange +5V lead" in note
