"""Shared plan/commit logic for writing or erasing a chip's memory (no board code)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from buspirate.exceptions import BusPirateError
from buspirate.mcp.jobs import _hex_bytes
from buspirate.mcp_bp6 import backup as backup_mod

CHANGED = ("plan again: the chip's contents changed since the backup "
           "(another chip, or another write); nothing was written")

WRITE_OPTIONS = {"operation": "write", "offset": 0, "file": None, "data_hex": None,
                 "length": None, "backup": True}


@dataclass(frozen=True)
class WriteJob:
    operation: str
    offset: int
    length: int
    data: Optional[bytes]
    source: str


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be a whole number, not %r" % (name, value))
    return value


def parse_job(opts: Dict[str, Any], size: int) -> WriteJob:
    operation = opts.get("operation", "write")
    if operation not in ("write", "erase"):
        raise ValueError("operation must be 'write' or 'erase', not %r" % (operation,))
    offset = _int(opts.get("offset", 0), "offset")
    if not 0 <= offset < size:
        raise ValueError("offset must be 0 to %d on this %d-byte chip, not %d"
                         % (size - 1, size, offset))
    file, data_hex, length = opts.get("file"), opts.get("data_hex"), opts.get("length")
    room = size - offset
    if operation == "erase":
        if file is not None or data_hex is not None:
            raise ValueError("an erase takes no file or data_hex")
        length = room if length is None else _int(length, "length")
        if not 1 <= length <= room:
            raise ValueError("length must be 1 to %d from offset %d, not %d"
                             % (room, offset, length))
        return WriteJob("erase", offset, length, None, "erase to 0xFF")
    if (file is None) == (data_hex is None):
        raise ValueError("a write needs exactly one of file or data_hex")
    if file is not None:
        path = Path(str(file)).expanduser()
        if not path.is_file():
            raise ValueError("file %s is not an existing regular file" % path)
        data = path.read_bytes()
        source = "file %s (sha256 %s)" % (path, hashlib.sha256(data).hexdigest())
    else:
        data = _hex_bytes(str(data_hex), "data_hex")
        source = "data_hex (%d bytes)" % len(data)
    if not 1 <= len(data) <= room:
        raise ValueError("the data must be 1 to %d bytes from offset %d, not %d"
                         % (room, offset, len(data)))
    return WriteJob("write", offset, len(data), data, source)


def _range(start: int, length: int) -> str:
    return "0x%06x-0x%06x" % (start, start + length - 1)


def prepare(job: WriteJob, read: Callable[[int, int], bytes], chip: str, label: str,
            keep_backup: bool, span: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    span_start, span_length = span if span is not None else (job.offset, job.length)
    if not (span_start <= job.offset and job.offset + job.length <= span_start + span_length):
        raise ValueError("the span %s must cover the whole job range %s"
                         % (_range(span_start, span_length), _range(job.offset, job.length)))
    old = bytes(read(span_start, span_length))
    if len(old) != span_length:
        raise ValueError("the chip returned %d bytes for a %d-byte read at 0x%06x"
                         % (len(old), span_length, span_start))
    saved = backup_mod.save(old, "%s-%06x" % (label, span_start)) if keep_backup else None
    where = "backup at %s" % saved["path"] if saved else "no backup (declined)"
    summary = "%s %s %s from %s; %s" % (chip, job.operation, _range(job.offset, job.length),
                                        job.source, where)
    return {"chip": chip, "operation": job.operation, "start": job.offset,
            "length": job.length, "summary": summary, "backup": saved,
            "span_start": span_start, "span_length": span_length, "source": job.source,
            "_job": job, "_old": old, "_sha": hashlib.sha256(old).hexdigest()}


def _hint(backup: Optional[Dict[str, Any]], lead: str) -> str:
    where = "the backup is at %s" % backup["path"] if backup else "no backup was saved"
    return "%s; %s" % (lead, where)


def commit(prepared: Dict[str, Any], read: Callable[[int, int], bytes],
           write_span: Callable[[int, bytes], None]) -> Dict[str, Any]:
    job, old = prepared["_job"], prepared["_old"]
    start, length = prepared["span_start"], prepared["span_length"]
    backup = prepared["backup"]
    writing = False
    try:
        now = bytes(read(start, length))
        if len(now) != length:
            return {"error": "the chip returned %d bytes for a %d-byte re-read; nothing was "
                             "written" % (len(now), length),
                    "verified": False, "backup": backup,
                    "hint": _hint(backup, "check the wiring and power, then plan again")}
        if hashlib.sha256(now).hexdigest() != prepared["_sha"]:
            return {"error": CHANGED}
        fill = job.data if job.data is not None else b"\xff" * job.length
        at = job.offset - start
        image = old[:at] + fill + old[at + job.length:]
        writing = True
        write_span(start, image)
        after = bytes(read(start, length))
        if len(after) != length:
            raise BusPirateError("the chip returned %d bytes reading back %d" % (len(after), length))
    except BusPirateError as exc:
        return {"error": str(exc), "verified": False, "backup": backup,
                "hint": _hint(backup, "the write failed part-way, so the chip may hold "
                                      "partial data; check the wiring and power") if writing
                else _hint(backup, "nothing was written; check the wiring and power, then "
                                   "plan again")}
    bad = [i for i in range(length) if after[i:i + 1] != image[i:i + 1]]
    result = {"written": job.length, "span_start": start, "span_length": length,
              "verified": not bad, "mismatches": len(bad),
              "first_bad": "0x%06x" % (start + bad[0]) if bad else None, "backup": backup}
    if bad:
        result["hint"] = _hint(backup, "the chip did not take the change — check its WP pin "
                                       "and write protection")
    return result
