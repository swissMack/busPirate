"""Serving the user guide from inside the dashboard.

The guide lives in ``docs/`` as Markdown and is the same text on GitHub, in an
editor, and in the UI — there is no second copy to drift.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

# docs/ sits next to the package, at the repository root.
DOCS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs")
)

#: Reading order for the sidebar. Anything else found is appended.
ORDER = [
    "user-guide",
    "macos-setup",
    "dashboard",
    "cli",
    "i2c",
    "spi",
    "uart",
    "onewire",
    "rawwire",
    "pins-and-power",
    "bus-pirate-v4",
    "bus-pirate-6",
    "troubleshooting",
    "protocol-reference",
    "extending",
]

_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


APP_GROUP = "This app"
OFFICIAL_GROUP = "Official Bus Pirate 5/6 manual"
#: The official manual, imported by scripts/import_official_docs.py.
OFFICIAL = "official"
BITPIRATE_GROUP = "ESP32 Bit Pirate wiki"
#: The Bit Pirate's own wiki, imported by scripts/import_bitpirate_wiki.py.
BITPIRATE_WIKI = "bitpirate-wiki"
#: Imported manuals by folder: their sidebar heading, and which board
#: variants list them. The Bit Pirate has far more in its terminal than the
#: dashboard drives, and its own wiki documents it; the Bus Pirate 5/6 manual
#: does not apply to it. Every page stays readable by name, so links work.
MANUALS = {
    OFFICIAL: {"group": OFFICIAL_GROUP, "for": lambda variant: variant != "bitpirate"},
    BITPIRATE_WIKI: {"group": BITPIRATE_GROUP, "for": lambda variant: variant == "bitpirate"},
}
#: Our page about a board, moved up to just after the user guide when that
#: board is the one in use.
BOARD_PAGE = {"bitpirate": "bitpirate", "bp6": "bus-pirate-6", "v4": "bus-pirate-v4"}
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
#: official/<section>/<page> is as deep as a page name goes.
MAX_DEPTH = 3


def _segments(name: str, depth: int = MAX_DEPTH) -> Optional[List[str]]:
    """A page or file name split safely, or None. No '..', no empty parts."""
    if not name or name.startswith("/") or "\\" in name:
        return None
    parts = name.split("/")
    if len(parts) > depth or any(not _SAFE_NAME.match(p) or p in (".", "..") for p in parts):
        return None
    return parts


def _inside(path: str) -> bool:
    """Whether ``path``, symlinks resolved, is still under docs/."""
    real, root = os.path.realpath(path), os.path.realpath(DOCS_DIR)
    return os.path.commonpath([real, root]) == root


def _title_of(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _page(name: str) -> Optional[Dict[str, str]]:
    path = os.path.join(DOCS_DIR, *name.split("/")) + ".md"
    try:
        with open(path, encoding="utf-8") as handle:
            head = handle.read(600)
    except OSError:
        return None
    folder = name.split("/", 1)[0] if "/" in name else None
    group = MANUALS[folder]["group"] if folder in MANUALS else APP_GROUP
    return {"name": name, "title": _title_of(head, name.rsplit("/", 1)[-1]), "group": group}


def _manual_order(folder: str) -> List[str]:
    try:
        with open(os.path.join(DOCS_DIR, folder, "order.json"), encoding="utf-8") as handle:
            return [n for n in json.load(handle) if isinstance(n, str) and _segments(n)]
    except (OSError, ValueError):
        return []


def available(variant: Optional[str] = None) -> List[Dict[str, str]]:
    """Our pages in reading order, then the manuals for ``variant``, each in its own order."""
    if not os.path.isdir(DOCS_DIR):
        return []
    names = sorted(
        entry[:-3]
        for entry in os.listdir(DOCS_DIR)
        if entry.endswith(".md") and _SAFE_NAME.match(entry)
    )
    ordered = [name for name in ORDER if name in names]
    ordered += [name for name in names if name not in ORDER]
    board_page = BOARD_PAGE.get(variant or "")
    if board_page in ordered and "user-guide" in ordered:
        ordered.remove(board_page)
        ordered.insert(ordered.index("user-guide") + 1, board_page)
    for folder, manual in MANUALS.items():
        if manual["for"](variant):
            ordered += _manual_order(folder)
    return [page for page in (_page(name) for name in ordered) if page is not None]


def read(name: str) -> Optional[str]:
    """One page's Markdown, or ``None`` if there is no such page.

    Only plain names are accepted, so a request cannot walk out of ``docs/``.
    """
    parts = _segments(name)
    if parts is None:
        return None
    path = os.path.join(DOCS_DIR, *parts) + ".md"
    if not os.path.isfile(path) or not _inside(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def file_path(relative: str) -> Optional[str]:
    """An image under docs/, or ``None`` for anything else.

    Image paths in the guides are relative to docs/ itself, e.g.
    ``official/images/fw/psu.png``.
    """
    parts = _segments(relative, depth=6)
    if parts is None:
        return None
    path = os.path.join(DOCS_DIR, *parts)
    if os.path.splitext(path)[1].lower() not in IMAGE_TYPES:
        return None
    if not os.path.isfile(path) or not _inside(path):
        return None
    return path


def search(query: str, limit: int = 20, variant: Optional[str] = None) -> List[Dict[str, str]]:
    """Pages matching every word of ``query``: title matches first, then by how often."""
    words = query.lower().split()
    if not words:
        return []
    scored = []
    for page in available(variant):
        text = read(page["name"]) or ""
        lower = text.lower()
        hits = sum(lower.count(word) for word in words)
        in_title = all(word in page["title"].lower() for word in words)
        if not in_title and not all(word in lower for word in words):
            continue
        first = min((lower.find(word) for word in words if word in lower), default=0)
        snippet = " ".join(text[max(0, first - 60): first + 100].split())
        scored.append(((0 if in_title else 1, -hits), dict(page, snippet=snippet)))
    scored.sort(key=lambda item: item[0])
    return [page for _, page in scored[:limit]]
