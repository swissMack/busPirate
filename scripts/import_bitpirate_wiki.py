"""Import the ESP32 Bit Pirate wiki into docs/bitpirate-wiki/ as plain Markdown.

The wiki (github.com/geo-tp/ESP32-Bit-Pirate/wiki) is a git repository of
GitHub-flavoured Markdown with inline HTML the app's viewer escapes rather
than renders: <img>, <details>/<summary>, <br>, <strong>. Those are turned
into Markdown here, wiki links become guide links, and every image is
downloaded so the guide works offline. The result is committed; re-run with
a newer --ref to update. Needs git, and Pillow (dev extras) to shrink images.

    .venv/bin/python scripts/import_bitpirate_wiki.py --ref <commit sha>
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict, List

WIKI = "https://github.com/geo-tp/ESP32-Bit-Pirate.wiki.git"
WIKI_WEB = "https://github.com/geo-tp/ESP32-Bit-Pirate/wiki"
LICENSE_URL = "https://raw.githubusercontent.com/geo-tp/ESP32-Bit-Pirate/{ref}/LICENSE"
OUT = Path(__file__).resolve().parent.parent / "docs" / "bitpirate-wiki"
PREFIX = "bitpirate-wiki"
#: Pages left on GitHub: page furniture, artwork for the project's own
#: promotion, and how to contribute to the firmware.
SKIP = {"_Footer", "_Sidebar", "99-Visual-Assets", "99-Contribute"}
#: Home first, then GitHub's own (alphabetical, numbered) order.
FIRST = "Home"
MAX_WIDTH = 1200
IMAGE_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
             "image/webp": ".webp", "image/svg+xml": ".svg"}

_IMG_TAG = re.compile(r"<img\b([^>]*)/?>", re.I)
_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")
_WIKI_LINK = re.compile(
    r"\]\((?:" + re.escape(WIKI_WEB) + r"/)?((?:\d\d-|Home)[\w.-]*)(#[^)]*)?\)"
)


def page_name(stem: str) -> str:
    return f"{PREFIX}/{stem.lower()}"


def fetch(url: str) -> tuple:
    request = urllib.request.Request(url, headers={"User-Agent": "busPirate-docs-import"})
    with urllib.request.urlopen(request, timeout=60) as reply:
        return reply.read(), reply.headers.get_content_type()


def save_image(url: str, cache: Dict[str, str]) -> str:
    """Download ``url`` once into images/, shrunk to MAX_WIDTH; its docs/ path.

    Animated GIFs (screen recordings, megabytes each) are kept as their first
    frame, as a PNG: enough to show the point in a guide.
    """
    if url in cache:
        return cache[url]
    data, kind = fetch(url)
    ext = IMAGE_EXT.get(kind)
    if ext is None:
        raise ValueError(f"{url} is {kind}, not an image")
    if ext != ".svg":
        try:
            from PIL import Image
        except ImportError:
            Image = None
        if Image is not None:
            image = Image.open(io.BytesIO(data))
            fmt = "PNG" if ext == ".gif" else image.format
            if ext == ".gif":
                image, ext = image.convert("RGB"), ".png"
            if image.width > MAX_WIDTH:
                image = image.resize(
                    (MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)),
                    Image.LANCZOS,
                )
            if fmt != image.format or image.width == MAX_WIDTH:
                buffer = io.BytesIO()
                image.save(buffer, format=fmt, optimize=True)
                data = buffer.getvalue()
    # Named by content, so one picture used under several URLs is kept once.
    name = hashlib.sha1(data).hexdigest()[:16] + ext
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "images" / name).write_bytes(data)
    cache[url] = f"{PREFIX}/images/{name}"
    return cache[url]


def convert(text: str, cache: Dict[str, str]) -> str:
    def img_tag(match: re.Match) -> str:
        attrs = dict(_ATTR.findall(match.group(1)))
        src = attrs.get("src", "")
        if not src.startswith("http"):
            return ""
        alt = html.unescape(attrs.get("alt", "")).replace("]", "")
        return f"![{alt}]({save_image(src, cache)})"

    text = _IMG_TAG.sub(img_tag, text)
    text = _MD_IMAGE.sub(lambda m: f"![{m.group(1)}]({save_image(m.group(2), cache)})", text)
    text = re.sub(r"<summary>\s*(.*?)\s*</summary>", r"\n**\1**\n", text, flags=re.S | re.I)
    text = re.sub(r"</?details[^>]*>", "", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "  \n", text, flags=re.I)
    text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text, flags=re.S | re.I)
    def wiki_link(match: re.Match) -> str:
        stem, anchor = match.group(1), match.group(2) or ""
        if stem in SKIP:  # not imported: send the reader to GitHub
            return f"]({WIKI_WEB}/{stem}{anchor})"
        return f"]({page_name(stem)}.md{anchor})"

    text = _WIKI_LINK.sub(wiki_link, text)
    return text.strip() + "\n"


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", required=True, help="wiki commit to import")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "wiki"
        subprocess.run(["git", "clone", "-q", WIKI, str(src)], check=True)
        subprocess.run(["git", "-C", str(src), "checkout", "-q", args.ref], check=True)
        stems = sorted(p.stem for p in src.glob("*.md") if p.stem not in SKIP)
        stems.sort(key=lambda s: (s != FIRST, s))
        footer = (src / "_Footer.md").read_text(encoding="utf-8").strip()

        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir(parents=True)
        cache: Dict[str, str] = {}
        for stem in stems:
            text = (src / f"{stem}.md").read_text(encoding="utf-8")
            if stem == FIRST:
                text += "\n\n" + footer
            (OUT / f"{stem.lower()}.md").write_text(convert(text, cache), encoding="utf-8")
            print(f"  {stem}")

    (OUT / "order.json").write_text(
        json.dumps([page_name(s) for s in stems], indent=1) + "\n", encoding="utf-8"
    )
    license_text, _ = fetch(LICENSE_URL.format(ref="main"))
    (OUT / "LICENSE").write_bytes(license_text)
    (OUT / "SOURCE.md").write_text(
        "# Source of the ESP32 Bit Pirate wiki\n\n"
        f"Converted from <{WIKI_WEB}> at commit `{args.ref}` by "
        "`scripts/import_bitpirate_wiki.py`. The ESP32 Bit Pirate project is "
        "MIT-licensed: see `LICENSE` in this folder.\n\n"
        "Do not edit these files by hand; re-run the script with a newer `--ref`.\n",
        encoding="utf-8",
    )
    print(f"{len(stems)} pages, {len(cache)} images -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
