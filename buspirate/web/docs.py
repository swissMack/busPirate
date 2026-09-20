"""Serving the user guide from inside the dashboard.

The guide lives in ``docs/`` as Markdown and is the same text on GitHub, in an
editor, and in the UI — there is no second copy to drift.
"""

from __future__ import annotations

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
    "troubleshooting",
    "protocol-reference",
    "extending",
]

_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _title_of(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def available() -> List[Dict[str, str]]:
    """Every guide page, in reading order."""
    if not os.path.isdir(DOCS_DIR):
        return []
    names = sorted(
        entry[:-3]
        for entry in os.listdir(DOCS_DIR)
        if entry.endswith(".md") and _SAFE_NAME.match(entry)
    )
    ordered = [name for name in ORDER if name in names]
    ordered += [name for name in names if name not in ORDER]
    pages = []
    for name in ordered:
        try:
            with open(os.path.join(DOCS_DIR, name + ".md"), encoding="utf-8") as handle:
                head = handle.read(600)
        except OSError:
            continue
        pages.append({"name": name, "title": _title_of(head, name)})
    return pages


def read(name: str) -> Optional[str]:
    """One page's Markdown, or ``None`` if there is no such page.

    Only plain names are accepted, so a request cannot walk out of ``docs/``.
    """
    if not _SAFE_NAME.match(name or "") or ".." in name:
        return None
    path = os.path.join(DOCS_DIR, name + ".md")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return handle.read()
