"""The in-app guide: our pages, the official manual, its images, and search."""

import json

import pytest

from buspirate.web import docs


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / "official" / "devices").mkdir(parents=True)
    (tmp_path / "official" / "images" / "fw").mkdir(parents=True)
    (tmp_path / "user-guide.md").write_text("# User guide\n\nStart here.\n")
    (tmp_path / "i2c.md").write_text("# I2C\n\nScan the bus.\n")
    (tmp_path / "official" / "index.md").write_text("# Bus Pirate manual\n")
    (tmp_path / "official" / "devices" / "24c02.md").write_text("# 24C02 EEPROM\n\nAn I2C eeprom. I2C I2C.\n")
    (tmp_path / "official" / "order.json").write_text(json.dumps(["official/index", "official/devices/24c02"]))
    (tmp_path / "official" / "images" / "fw" / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "bitpirate.md").write_text("# ESP32 Bit Pirate\n\nIts terminal.\n")
    (tmp_path / "bitpirate-wiki").mkdir()
    (tmp_path / "bitpirate-wiki" / "05-i2c.md").write_text("# I2C Mode\n\nscan, sniff, eeprom.\n")
    (tmp_path / "bitpirate-wiki" / "order.json").write_text(json.dumps(["bitpirate-wiki/05-i2c"]))
    (tmp_path / "secret.txt").write_text("no")
    monkeypatch.setattr(docs, "DOCS_DIR", str(tmp_path))
    return tmp_path


def test_pages_are_grouped(tree):
    pages = docs.available()
    assert [p["name"] for p in pages] == [
        "user-guide", "i2c", "bitpirate", "official/index", "official/devices/24c02",
    ]
    assert pages[0]["group"] == "This app"
    assert pages[-1]["group"] == "Official Bus Pirate 5/6 manual"
    assert pages[-1]["title"] == "24C02 EEPROM"


def test_nested_pages_are_read(tree):
    assert docs.read("official/devices/24c02").startswith("# 24C02")


@pytest.mark.parametrize("name", ["../secret", "official/../../x", "/etc/passwd", "official//x", "a/b/c/d"])
def test_bad_names_are_refused(tree, name):
    assert docs.read(name) is None


def test_images_are_served(tree):
    assert docs.file_path("official/images/fw/a.png").endswith("a.png")


@pytest.mark.parametrize("path", ["secret.txt", "../x.png", "official/images/../../secret.txt", "/etc/hosts"])
def test_doc_files_cannot_escape_the_docs_directory(tree, path):
    assert docs.file_path(path) is None


def test_doc_files_refuse_symlinks_out(tree, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "x.png"
    outside.write_bytes(b"\x89PNG")
    (tree / "official" / "images" / "link.png").symlink_to(outside)
    assert docs.file_path("official/images/link.png") is None


def test_search_puts_title_matches_first(tree):
    results = docs.search("i2c")
    assert results[0]["name"] == "i2c"
    assert {r["name"] for r in results} == {"i2c", "official/devices/24c02"}
    assert "I2C" in results[1]["snippet"]


def test_empty_search(tree):
    assert docs.search("  ") == []


def test_a_bit_pirate_gets_its_own_wiki_instead_of_the_bus_pirate_manual(tree):
    pages = docs.available("bitpirate")
    names = [p["name"] for p in pages]
    assert names == ["user-guide", "bitpirate", "i2c", "bitpirate-wiki/05-i2c"]
    assert pages[-1]["group"] == "ESP32 Bit Pirate wiki"
    assert pages[-1]["title"] == "I2C Mode"


@pytest.mark.parametrize("variant", [None, "v3", "v4", "bp6"])
def test_bus_pirates_get_the_official_manual_and_not_the_wiki(tree, variant):
    names = [p["name"] for p in docs.available(variant)]
    assert "official/index" in names
    assert not any(n.startswith("bitpirate-wiki/") for n in names)


def test_search_follows_the_board(tree):
    assert {r["name"] for r in docs.search("sniff", variant="bitpirate")} == {"bitpirate-wiki/05-i2c"}
    assert docs.search("sniff") == []


def test_wiki_pages_stay_readable_whatever_the_board(tree):
    assert docs.read("bitpirate-wiki/05-i2c").startswith("# I2C Mode")
