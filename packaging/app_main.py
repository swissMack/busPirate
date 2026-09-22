"""Entry point for the frozen BusPirate.app.

The bundle is a different artifact from ``bin/BusPirate.app``: that one is a
thin shim that runs the repo's ``bin/dashboard.command``, while this is the
whole dashboard frozen with its interpreter, so it needs no Python and no
checkout. All it does is open the window; every decision about how the
server and the window work still lives in ``buspirate.web.window``.
"""

from __future__ import annotations

import multiprocessing
import sys


def _alert(message: str) -> None:
    """Say something when there is no terminal to print to."""
    import subprocess

    try:
        subprocess.run(
            [
                "/usr/bin/osascript",
                "-e",
                'display alert "Bus Pirate" message '
                f"{_applescript_string(message)} as critical",
            ],
            check=False,
            capture_output=True,
        )
    except OSError:
        pass


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    multiprocessing.freeze_support()
    from buspirate.web.window import run_window

    try:
        note = run_window()
    except Exception as exc:  # noqa: BLE001 - last resort, there is no console
        print(f"buspirate: {exc}", file=sys.stderr)
        _alert(str(exc))
        return 1
    if note:
        print(note, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
