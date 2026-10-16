"""Import the official Bus Pirate 5/6 manual into docs/official/ as plain Markdown.

The manual (docs.buspirate.com) is a Hugo site in
DangerousPrototypes/BusPirate-docs-hugo, MIT-licensed. Its pages use Hugo
shortcodes the app's viewer cannot render, so they are converted here once,
and the result is committed. Re-run with a newer --ref to update. Needs
Python 3.9+ and, to shrink the images, Pillow (in the dev extras).

    .venv/bin/python scripts/import_official_docs.py --ref <commit sha>
"""

from __future__ import annotations

import argparse
import datetime
import html
import io
import json
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Tuple

REPO = "DangerousPrototypes/BusPirate-docs-hugo"
SITE = "https://docs.buspirate.com"
#: Top-level pages and sections kept; hardware, manufacturing, enclosure,
#: development, downloads and the rest are left on the website.
KEEP_FILES = {"_index.md", "command-reference.md", "license.md"}
KEEP_DIRS = {"tutorial-basics", "devices", "overview", "logic-analyzer",
             "binmode-reference", "software", "cables"}
MAX_WIDTH = 1200
ALERT_KINDS = {"info": "Note", "warning": "Warning", "danger": "Danger", "success": "Tip"}

_FRONT = re.compile(r"\A\+\+\+\n(.*?)\n\+\+\+\n?", re.S)
_TITLE = re.compile(r"""^title\s*=\s*['"](.*)['"]\s*$""", re.M)
_WEIGHT = re.compile(r"^weight\s*=\s*(\d+)\s*$", re.M)
# Hugo shortcodes come as {{< x >}} or {{% x %}}, closing tags sometimes as
# {{</ x>}}; every pattern below accepts all three (forms seen at efa4e5e).
_O, _C = r"\{\{[<%]\s*", r"\s*[>%]\}\}"
_ALERT = re.compile(_O + r'alert\s+context="(\w+)"' + _C + r"(.*?)" + _O + r"/\s*alert" + _C, re.S)
_TERM = re.compile(_O + r"term\b[^}]*?" + _C + r"(.*?)" + _O + r"/\s*term" + _C, re.S)
_TERMFILE = re.compile(_O + r'termfile\s+source="([^"]+)"' + _C)
_READFILE = re.compile(_O + r'readfile\s+"([^"]+)"' + _C)
_RELREF = re.compile(_O + r'relref\s+"([^"]+)"' + _C)
_TAB = re.compile(_O + r'tab\s+(?:(?:name|tabName)=)?"([^"]+)"' + _C)
_TABS_OR_END = re.compile(_O + r"/?\s*tabs\b[^}]*?" + _C + "|" + _O + r"/\s*tab" + _C)
_ASCIICAST = re.compile(_O + r"asciicast\b[^}]*?" + _C)
_BTN = re.compile(_O + r'btn\b[^}]*?href="([^"]+)"[^}]*?' + _C + r"(.*?)" + _O + r"/\s*btn" + _C, re.S)
_YEAR = re.compile(_O + r"year" + _C)
_ANY = re.compile(r"\{\{[<%]\s*(/?[\w-]+)[^}]*[>%]\}\}")
_IMAGE = re.compile(r"(!\[[^\]]*\]\()/images/docs/([^)\s]+)\)")


def slug(text: str) -> str:
    """A heading's anchor, the way Hugo makes it (no trimming: a heading that
    starts with a symbol, like "`:` Repeat", keeps a leading dash)."""
    text = re.sub(r"<[^>]+>", "", text.lower())
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s", "-", text)


def _plain(markup: str) -> str:
    """Coloured terminal HTML as the plain text a terminal would show."""
    text = re.sub(r"<br\s*/?>", "\n", markup)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    return "\n".join(line.rstrip() for line in text.strip("\n").splitlines())


def _without_suffix(text: str, suffix: str) -> str:
    # str.removesuffix is Python 3.9+, and CI still runs 3.8.
    return text[: -len(suffix)] if suffix and text.endswith(suffix) else text


def _relref(target: str) -> str:
    path, _, anchor = target.partition("#")
    # Some links were written against a local preview server.
    path = re.sub(r"^https?://[^/]+", "", path).strip("/")
    if path.endswith(".md"):
        path = path[:-3]
    if path.startswith("docs/"):
        path = path[len("docs/"):]
    path = path.strip("/")
    suffix = f"#{anchor}" if anchor else ""
    first = path.split("/")[0] if path else ""
    if path and first not in KEEP_DIRS and f"{path}.md" not in KEEP_FILES:
        # A page that is not bundled (hardware, downloads, ...): the website.
        return f"{SITE}/docs/{path}/{suffix}"
    if not path:
        name = "official/index"
    elif path in KEEP_DIRS:
        name = f"official/{path}/index"
    else:
        name = f"official/{path}"
    return f"{name}.md{suffix}"


def convert_page(text: str, page_path: str, repo: Path, report: List[str]) -> Tuple[str, str, int]:
    """One Hugo page as plain Markdown: ``(markdown, title, weight)``."""
    title, weight = Path(page_path).stem, 0
    front = _FRONT.match(text)
    if front:
        found = _TITLE.search(front.group(1))
        title = found.group(1) if found else title
        found = _WEIGHT.search(front.group(1))
        weight = int(found.group(1)) if found else 0
        text = text[front.end():]

    def readfile(match):
        path = repo / match.group(1).lstrip("/")
        if not path.is_file():
            report.append(f"{page_path}: readfile {match.group(1)} not found")
            return ""
        inner = _FRONT.sub("", path.read_text(encoding="utf-8"))
        return convert_page(inner, page_path, repo, report)[0].split("\n", 2)[-1]

    def alert(match):
        kind = ALERT_KINDS.get(match.group(1), "Note")
        lines = match.group(2).strip("\n").splitlines()
        return "\n".join([f"> **{kind}:**"] + [f"> {line}".rstrip() for line in lines])

    def termfile(match):
        path = repo / match.group(1)
        if not path.is_file():
            report.append(f"{page_path}: termfile {match.group(1)} not found")
            return ""
        return "```text\n" + _plain(path.read_text(encoding="utf-8")) + "\n```"

    def unknown(match):
        report.append(f"{page_path}: dropped shortcode {match.group(1)}")
        return ""

    page_url = _without_suffix(_without_suffix(page_path.replace("content/", ""), ".md"), "/_index") + "/"
    text = _READFILE.sub(readfile, text)
    text = _ALERT.sub(alert, text)
    text = _TERM.sub(lambda m: "```text\n" + _plain(m.group(1)) + "\n```", text)
    text = _TERMFILE.sub(termfile, text)
    text = _RELREF.sub(lambda m: _relref(m.group(1)), text)
    text = _TAB.sub(lambda m: f"#### {m.group(1)}", text)
    text = _TABS_OR_END.sub("", text)
    text = _ASCIICAST.sub(f"[▶ Watch this as a recording on docs.buspirate.com]({SITE}/{page_url})", text)
    text = _BTN.sub(lambda m: f"[{m.group(2).strip()}]({m.group(1)})", text)
    text = _YEAR.sub(str(datetime.date.today().year), text)
    text = _ANY.sub(unknown, text)
    text = _IMAGE.sub(lambda m: f"{m.group(1)}official/images/{m.group(2)})", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
    return f"# {title}\n\n{text}\n", title, weight


def _fetch(ref: str, into: Path) -> Path:
    url = f"https://codeload.github.com/{REPO}/tar.gz/{ref}"
    with urllib.request.urlopen(url) as response:  # noqa: S310 - fixed https URL
        data = response.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        try:
            archive.extractall(into, filter="data")
        except TypeError:  # Python without the extraction filter
            archive.extractall(into)
    return next(into.iterdir())


def _copy_image(source: Path, target: Path, report: List[str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
    except ImportError:
        report.append("Pillow missing: images copied at full size")
        shutil.copyfile(source, target)
        return
    if source.suffix.lower() in {".svg", ".gif"}:
        shutil.copyfile(source, target)
        return
    with Image.open(source) as image:
        if image.width > MAX_WIDTH:
            image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)))
        options = {"quality": 85} if target.suffix.lower() in {".jpg", ".jpeg"} else {}
        image.save(target, optimize=True, **options)


def _kept(rel: Path) -> bool:
    if len(rel.parts) == 1:
        return rel.name in KEEP_FILES
    return rel.parts[0] in KEEP_DIRS


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", required=True, help="commit SHA of BusPirate-docs-hugo")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "official"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    report: List[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = _fetch(args.ref, Path(tmp))
        content = repo / "content" / "docs"
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        pages = []
        for source in sorted(content.rglob("*.md")):
            rel = source.relative_to(content)
            if not _kept(rel):
                continue
            markdown, title, weight = convert_page(
                source.read_text(encoding="utf-8"), f"content/docs/{rel.as_posix()}", repo, report)
            name = rel.with_name("index.md") if rel.name == "_index.md" else rel
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(markdown, encoding="utf-8")
            for image in re.findall(r"\]\(official/images/([^)\s]+)\)", markdown):
                found = repo / "assets" / "images" / "docs" / image
                if found.is_file():
                    if not (out / "images" / image).exists():
                        _copy_image(found, out / "images" / image, report)
                else:
                    report.append(f"{rel}: image {image} not found")
            section = name.parts[0] if len(name.parts) > 1 else ""
            is_index = name.name == "index.md"
            pages.append(((section, 0 if is_index else 1, weight, str(name)),
                          "official/" + name.with_suffix("").as_posix()))
        pages.sort()
        top = [p for p in pages if p[0][0] == ""]
        rest = [p for p in pages if p[0][0] != ""]
        (out / "order.json").write_text(json.dumps([n for _, n in top + rest], indent=1) + "\n")
        shutil.copyfile(repo / "LICENSE", out / "LICENSE")
    (out / "SOURCE.md").write_text(
        "# Source of the official manual\n\n"
        f"Converted from <https://github.com/{REPO}> at commit `{args.ref}` by "
        "`scripts/import_official_docs.py`. MIT licence: see `LICENSE` in this folder.\n\n"
        "Do not edit these files by hand; re-run the script with a newer `--ref`.\n",
        encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"{len(pages)} pages, {size / 1e6:.1f} MB in {out}")
    for line in report:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
