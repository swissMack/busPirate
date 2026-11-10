"""Save bytes read from a chip as a timestamped file that is never overwritten."""

from __future__ import annotations

import datetime
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional


def save(data: bytes, what: str, folder: Optional[Path] = None,
         now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """Write ``<folder>/<what>-<YYYYmmdd-HHMMSS>.bin`` (``-2``, ``-3`` ... if taken)."""
    folder = Path(folder) if folder is not None else Path.home() / "BusPirate" / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    n = 1
    while True:
        name = "%s-%s%s.bin" % (what, stamp, "" if n == 1 else "-%d" % n)
        path = folder / name
        try:
            with open(str(path), "xb") as fh:  # exclusive: never clobbers
                fh.write(data)
            break
        except FileExistsError:
            n += 1
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
