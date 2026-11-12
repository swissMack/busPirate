"""The Bus Pirate's own disk (its NAND drive): list, show, hex and delete.

The disk commands are global, so these recipes stay in HiZ and need no supply
and no wiring. ``disk-delete`` removes a file for good (the firmware asks
nothing), so it only prepares and needs its own yes.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Union

from ...bp6 import disk
from ...bp6.console import TerminalError
from . import Recipe, register

Options = Dict[str, Any]

SOURCE = "https://docs.buspirate.com/docs/command-reference/"
WORDS = ("disk", "files", "file", "storage", "nand", "drive", "usb drive")
READ_ONLY = ("the computer sees the disk read-only while the terminal is in use",)
MAX_CHARS = 65536
PATH_HINT = ("give path as a short (8.3) name from the disk's root, such as /bpconfig.bp; "
             "run disk-list to see what is there")


def _bad(error: str, hint: str = PATH_HINT) -> Dict[str, Any]:
    return {"ok": False, "error": error, "hint": hint}


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _find(con: Any, path: Any) -> Union[str, Tuple[str, Dict[str, Any]]]:
    """The normalised path and its entry in the parent's listing, or why not.

    Lists the parent directory, so a missing file, a directory and a missing
    parent are each named before anything reads or changes the file.
    """
    try:
        where = disk.check_path(path)
    except ValueError as exc:
        return str(exc)
    parent, name = where.rsplit("/", 1)
    try:
        listed = disk.listing(con, parent or "/")
    except TerminalError as exc:
        return str(exc)
    if name in listed["dirs"]:
        return "%s is a directory, not a file" % where
    entry = next((f for f in listed["files"]
                  if f["name"] == name), None)  # type: Optional[Dict[str, Any]]
    if entry is None:
        return "no file named %s on the Bus Pirate's disk" % where
    return where, entry


def _list_check(con: Any, opts: Options) -> Dict[str, Any]:
    try:
        disk.listing(con, opts.get("path"))
    except (ValueError, TerminalError) as exc:
        return _bad(str(exc))
    return {"ok": True}


def _list(con: Any, opts: Options) -> Dict[str, Any]:
    return disk.listing(con, opts["path"])


def _show_check(con: Any, opts: Options) -> Dict[str, Any]:
    chars = opts.get("max_chars")
    if not _whole(chars) or not 1 <= chars <= MAX_CHARS:
        return _bad("max_chars must be 1 to %d characters, not %r" % (MAX_CHARS, chars),
                    "fix max_chars and plan again")
    found = _find(con, opts.get("path"))
    if isinstance(found, str):
        return _bad(found)
    size = found[1]["size"]
    if size > chars:
        return _bad("%s is %d bytes, more than max_chars (%d): read it with disk-hex, or "
                    "raise max_chars (up to %d)" % (found[0], size, chars, MAX_CHARS),
                    "use disk-hex for a large or binary file")
    return {"ok": True, "size": size}


def _show(con: Any, opts: Options) -> Dict[str, Any]:
    return disk.show(con, opts["path"], opts["max_chars"])


def _hex_check(con: Any, opts: Options) -> Dict[str, Any]:
    start, length = opts.get("start"), opts.get("length")
    if not _whole(start) or start < 0:
        return _bad("start must be a byte offset from 0, not %r" % (start,),
                    "fix start and plan again")
    if not _whole(length) or not 1 <= length <= disk.MAX_HEX:
        return _bad("length must be 1 to %d bytes, not %r" % (disk.MAX_HEX, length),
                    "fix length and plan again; read a bigger file in several runs")
    found = _find(con, opts.get("path"))
    if isinstance(found, str):
        return _bad(found)
    return {"ok": True, "size": found[1]["size"]}


def _hex(con: Any, opts: Options) -> Dict[str, Any]:
    return disk.hexdump(con, opts["path"], opts["start"], opts["length"])


def _delete_check(con: Any, opts: Options) -> Dict[str, Any]:
    found = _find(con, opts.get("path"))
    if isinstance(found, str):
        return _bad(found)
    where, entry = found
    return {"ok": True, "identity": "%s:%d:%s" % (where, entry["size"], entry["date"]),
            "size": entry["size"]}


def _prepare(con: Any, opts: Options) -> Dict[str, Any]:
    """Only names the file; ``_commit`` deletes it."""
    found = _find(con, opts["path"])
    if isinstance(found, str):  # the check passed a moment ago, so this is unexpected
        raise TerminalError(found)
    where, entry = found
    summary = ("Delete %s (%d bytes) from the Bus Pirate's disk. It cannot be undone; copy it "
               "from the Bus Pirate's USB drive first if it is needed." % (where, entry["size"]))
    return {"chip": "Bus Pirate disk", "operation": "delete", "start": 0,
            "length": entry["size"], "summary": summary, "backup": None, "_path": where}


def _commit(con: Any, opts: Options, prepared: Dict[str, Any]) -> Dict[str, Any]:
    where = prepared["_path"]
    out = disk.delete(con, where)
    gone = _find(con, where)
    out["path"] = where
    out["verified"] = isinstance(gone, str) and gone.startswith("no file")
    if not out["verified"]:
        out["hint"] = "the firmware took 'rm' but %s is still listed" % where
    return out


_COMMON = dict(bus="board", transport="terminal", terminal_mode=None, default_mv=0,
               min_mv=0, max_mv=0, milliamps=0, pullups=False, wiring=(),
               source=SOURCE)  # type: Dict[str, Any]

register(Recipe(
    name="disk-list", title="Bus Pirate disk: list the files and directories in a directory",
    words=WORDS + ("ls", "dir", "list files"), options={"path": "/"},
    check=_list_check, action=_list, notes=READ_ONLY, **_COMMON))

register(Recipe(
    name="disk-show", title="Bus Pirate disk: show a text file",
    words=WORDS + ("cat", "show file", "read file", "text", "config"),
    options={"path": None, "max_chars": 16384}, check=_show_check, action=_show,
    notes=READ_ONLY + ("use disk-hex for binary files",
                       "the firmware prints each line with printf, so a % in the file "
                       "comes back mangled; use disk-hex to see the exact bytes"),
    **_COMMON))

register(Recipe(
    name="disk-hex", title="Bus Pirate disk: hex dump of part of a file",
    words=WORDS + ("hex", "hexdump", "dump", "binary", "read file"),
    options={"path": None, "start": 0, "length": 256}, check=_hex_check, action=_hex,
    notes=READ_ONLY, **_COMMON))

register(Recipe(
    name="disk-delete", title="Bus Pirate disk: delete a file (asks for its own yes)",
    words=WORDS + ("rm", "delete", "delete file", "remove file", "erase file"),
    options={"path": None}, risk="destructive", check=_delete_check, action=_prepare,
    commit=_commit,
    notes=READ_ONLY + ("a deleted file cannot be recovered; copy it from the Bus Pirate's "
                       "USB drive first",),
    **_COMMON))
