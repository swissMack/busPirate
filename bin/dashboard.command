#!/bin/bash
# Double-click this in Finder to open the Bus Pirate dashboard.
# It sets up a Python environment the first time, then starts the server and
# opens your browser. Close the Terminal window or press Ctrl-C to stop.

set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
VENV="$REPO/.venv"
PYTHON_MIN="3.8"

echo "busPirate dashboard"
echo "-------------------"

find_python() {
  for candidate in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c "import sys; raise SystemExit(sys.version_info < (3, 8))"; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

if [ ! -x "$VENV/bin/python" ]; then
  PY="$(find_python)" || {
    echo "No Python $PYTHON_MIN or newer found."
    echo "Install it from https://www.python.org/downloads/macos/ and run this again."
    read -r -p "Press Return to close." _
    exit 1
  }
  echo "First run: creating a Python environment in .venv (this takes a minute)…"
  "$PY" -m venv "$VENV"
fi

# Install or update the package whenever the project metadata has changed.
STAMP="$VENV/.installed"
if [ ! -f "$STAMP" ] || [ "$REPO/pyproject.toml" -nt "$STAMP" ]; then
  echo "Installing dependencies…"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -e "$REPO[web]"
  touch "$STAMP"
fi

echo
"$VENV/bin/python" -m buspirate ports || true
echo
echo "Starting the dashboard. Press Ctrl-C to stop."
exec "$VENV/bin/python" -m buspirate dashboard "$@"
