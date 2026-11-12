"""The Bus Pirate's own disk (its NAND drive) through the terminal's global commands.

``ls -l <dir>``, ``cat <file>``, ``hex <file> -s <start> -b <bytes> -c`` and
``rm <file>`` work in every mode. The disk is FAT with short names only (8.3,
printed lower case) and the firmware keeps a path in a 32-byte buffer, so a
path is at most 31 characters. ``check_path`` refuses anything else before a
line is sent, and makes every path absolute (from the disk's root), so the
terminal's current directory never matters.

FatFs errors print ``Error: <reason>`` with no line ending (the prompt follows
on that line); ``Console.command`` keeps that line as the reply's error, and
each helper raises ``TerminalError`` with it. A missing directory makes
``ls -l`` print nothing at all, so a listing without its ``N dirs, M files``
line is reported as no such directory.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .console import TerminalError

MAX_PATH = 31
MAX_HEX = 4096
#: One 8.3 component: a name of 1-8 characters and an optional extension of 1-3.
_COMPONENT = re.compile(r"[a-z0-9_\-~]{1,8}(?:\.[a-z0-9_\-~]{1,3})?")
_ALLOWED = re.compile(r"[A-Za-z0-9_\-~./]+")
_DATE = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})"
_DIR_LINE = re.compile(r"^\s*-\s+" + _DATE + r"\s+(\S+)/\s*$")
_FILE_LINE = re.compile(r"^\s*(\d+)\s+" + _DATE + r"\s+(\S+)\s*$")
_SUMMARY = re.compile(r"^\s*(\d+)\s+dirs?,\s*(\d+)\s+files?\s*$", re.I)
#: A row of ``hex -c`` (ui/ui_hex.c): ``%08X: `` then up to 16 ``%02X `` then ``|ascii|``.
#: Rows are aligned to 16 bytes, so the first and last rows can hold bytes
#: outside the request (the firmware only greys them, which the console strips).
_HEX_ROW = re.compile(r"^([0-9A-Fa-f]{8}): ((?:[0-9A-Fa-f]{2} ){1,16})")


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_path(path: Any, directory: bool = False) -> str:
    """``path`` made absolute and lower case, or ``ValueError`` saying why not.

    A file path may not end in ``/``; a directory path may (``/`` is the root).
    """
    what = "directory" if directory else "file"
    if not isinstance(path, str) or not path:
        raise ValueError("path must name a %s on the Bus Pirate's disk, such as %s, not %r"
                         % (what, "/dumps" if directory else "/bpconfig.bp", path))
    if not _ALLOWED.fullmatch(path):
        raise ValueError("path %r may use only letters, digits, _ - ~ . and /" % path)
    if path.endswith("/") and not directory:
        raise ValueError("path %r ends in /, so it names a directory, not a file" % path)
    parts = path.strip("/").split("/") if path.strip("/") else []
    if not parts and not directory:
        raise ValueError("path %r names the root directory, not a file" % path)
    for part in parts:
        if part in (".", ".."):
            raise ValueError("path %r may not use . or .." % path)
        if not _COMPONENT.fullmatch(part.lower()):
            raise ValueError("path %r: %r is not a short (8.3) name: up to 8 characters, "
                             "then optionally a dot and up to 3" % (path, part))
    out = "/" + "/".join(p.lower() for p in parts)
    if len(out) > MAX_PATH:
        raise ValueError("path %r is %d characters from the root; the Bus Pirate takes at "
                         "most %d" % (path, len(out), MAX_PATH))
    return out


def _run(con: Any, line: str, timeout: float = 3.0) -> str:
    reply = con.command(line, timeout=timeout)
    if reply.error:
        raise TerminalError("'%s' failed: %s" % (line, reply.error))
    return reply.text


def listing(con: Any, path: str = "/") -> Dict[str, Any]:
    """The directories and files in ``path`` (sizes in bytes, dates as printed)."""
    where = check_path(path, directory=True)
    line = "ls -l %s" % where
    text = _run(con, line)
    dirs = []  # type: List[str]
    files = []  # type: List[Dict[str, Any]]
    summary = None
    for ln in text.split("\n"):
        m = _DIR_LINE.match(ln)
        if m:
            dirs.append(m.group(2).lower())
            continue
        m = _FILE_LINE.match(ln)
        if m:
            files.append({"name": m.group(3).lower(), "size": int(m.group(1)),
                          "date": m.group(2)})
            continue
        summary = _SUMMARY.match(ln) or summary
    if summary is None:
        raise TerminalError("'%s': no such directory on the Bus Pirate's disk" % line)
    return {"path": where, "dirs": dirs, "files": files}


def show(con: Any, path: str, max_chars: int = 16384) -> Dict[str, Any]:
    """The text of a file, cut at ``max_chars``.

    ``cat`` prints each line with ``printf``, so a ``%`` in the file comes back mangled.
    """
    if not _whole(max_chars) or max_chars < 1:
        raise ValueError("max_chars must be a whole number of characters from 1, not %r"
                         % (max_chars,))
    text = _run(con, "cat %s" % check_path(path), timeout=15.0)
    return {"text": text[:max_chars], "truncated": len(text) > max_chars}


def hexdump(con: Any, path: str, start: int = 0, length: int = 256) -> Dict[str, Any]:
    """Up to ``length`` bytes from offset ``start`` (fewer at the end of the file)."""
    if not _whole(start) or start < 0:
        raise ValueError("start must be a byte offset from 0, not %r" % (start,))
    if not _whole(length) or not 1 <= length <= MAX_HEX:
        raise ValueError("length must be 1 to %d bytes, not %r" % (MAX_HEX, length))
    text = _run(con, "hex %s -s %d -b %d -c" % (check_path(path), start, length),
                timeout=15.0)
    data = bytearray()
    end = start + length
    for ln in text.split("\n"):
        m = _HEX_ROW.match(ln)
        if not m:
            continue
        at = int(m.group(1), 16)
        for i, byte in enumerate(bytes.fromhex(m.group(2))):
            if start <= at + i < end and at + i == start + len(data):
                data.append(byte)
    out = {"start": start, "data_hex": bytes(data).hex(),
           "length": len(data)}  # type: Dict[str, Any]
    if len(data) < length:
        out["note"] = ("%d of the %d bytes asked for: the file ended at byte %d"
                       % (len(data), length, start + len(data)))
    return out


def delete(con: Any, path: str) -> Dict[str, Any]:
    """Delete a file. The firmware asks nothing first."""
    _run(con, "rm %s" % check_path(path), timeout=10.0)
    return {"deleted": True}
