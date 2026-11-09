"""Knowledge for an AI client: distilled notes, and search over the bundled docs.

The notes (``notes/*.md``) are short, cited summaries, one per topic, that the
client reads before acting. ``search`` covers the notes and, when the repo's
``docs/`` folder is next to the package, the guides, the Bus Pirate 5/6 manual
(``docs/official/``) and the Bit Pirate wiki (``docs/bitpirate-wiki/``). An
installed wheel has no ``docs/``, so there it searches the notes alone.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

NOTES_DIR = Path(__file__).resolve().parent / "notes"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC_GLOBS = ("*.md", "official/**/*.md", "bitpirate-wiki/*.md")
_EXCERPT_CHARS = 300
_WORD = re.compile(r"[a-z0-9]+")
# Words too common to tell sections apart ("how do I read the sensor").
_STOPWORDS = frozenset(
    "a an and are be can do does for how i in is it my of on or the to what "
    "when where which why with".split())


def _docs_root() -> Optional[Path]:
    docs = _REPO_ROOT / "docs"
    return docs if docs.is_dir() else None


def _note_paths() -> Dict[str, Path]:
    return {p.stem: p for p in sorted(NOTES_DIR.glob("*.md"))}


def _title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def topics() -> List[Dict[str, str]]:
    """Every note, as ``{"topic", "title"}``; the title is its ``# `` line."""
    return [{"topic": name, "title": _title(path.read_text(encoding="utf-8"))}
            for name, path in _note_paths().items()]


def read(topic: str) -> str:
    """The text of one note. KeyError, listing the valid topics, if unknown."""
    paths = _note_paths()
    if topic not in paths:
        raise KeyError("unknown topic %r; valid topics: %s" % (topic, ", ".join(paths)))
    return paths[topic].read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _sections(path: Path) -> Tuple[Tuple[str, str], ...]:
    """``(heading, body)`` pairs, split on ``## `` headings.

    The text before the first ``## `` is filed under the page's ``# `` title.
    A note's closing ``Sources:`` list is left out: its URLs would otherwise
    score for the section above it. ``read()`` still returns it.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    heading = _title(text) or path.stem
    out = []
    lines: List[str] = []
    for line in text.splitlines():
        if line.strip() == "Sources:":
            break
        if line.startswith("## "):
            out.append((heading, "\n".join(lines)))
            heading, lines = line[3:].strip(), []
        else:
            lines.append(line)
    out.append((heading, "\n".join(lines)))
    return tuple((h, b) for h, b in out if b.strip())


def _words(text: str) -> List[str]:
    return _WORD.findall(text.lower())


def _excerpt(body: str, query: List[str]) -> str:
    lines = [ln for ln in body.splitlines() if ln.strip()]
    start = 0
    for i, line in enumerate(lines):
        if set(_words(line)) & set(query):
            start = i
            break
    text = " ".join(ln.strip() for ln in lines[start:])
    if len(text) > _EXCERPT_CHARS:
        text = text[:_EXCERPT_CHARS].rsplit(" ", 1)[0] + " …"
    return text


def _sources() -> List[Tuple[str, Path]]:
    found = [("notes/" + p.name, p) for p in _note_paths().values()]
    docs = _docs_root()
    if docs is not None:
        seen = set()
        for pattern in _DOC_GLOBS:
            for path in sorted(docs.glob(pattern)):
                if path.is_file() and path not in seen:
                    seen.add(path)
                    found.append(("docs/" + path.relative_to(docs).as_posix(), path))
    return found


def search(query: str, limit: int = 8) -> List[Dict[str, str]]:
    """Sections of the notes and bundled docs that contain the query's words.

    A section scores one point per distinct query word it contains (heading
    included; common words such as "the" and "how" are ignored). Higher
    scores come first; on equal scores, notes come before the docs, then
    sections that mention the words more often.
    Returns ``[{"source", "heading", "excerpt"}]``.
    """
    query_words = sorted(set(_words(query)) - _STOPWORDS)
    if not query_words or limit <= 0:
        return []
    wanted = set(query_words)
    scored = []
    for order, (source, path) in enumerate(_sources()):
        is_doc = 0 if source.startswith("notes/") else 1
        for heading, body in _sections(path):
            words = _words(heading + "\n" + body)
            present = set(words)
            score = sum(1 for w in query_words if w in present)
            if score:
                hits = sum(1 for w in words if w in wanted)
                scored.append((-score, is_doc, -hits, order, source, heading, body))
    scored.sort(key=lambda s: s[:4])
    return [{"source": source, "heading": heading, "excerpt": _excerpt(body, query_words)}
            for _, _, _, _, source, heading, body in scored[:limit]]
