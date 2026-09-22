#!/bin/bash
# Double-click this in Finder to open the Bus Pirate dashboard.
# It sets up a Python environment the first time, then starts the server and
# opens the dashboard in its own window — falling back to your browser if
# the window can't start. Close the window (or the Terminal, or Ctrl-C) to
# stop.

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
  # The window is a bonus, not a requirement: if the GUI toolkit will not
  # install, the browser dashboard must still work.
  "$VENV/bin/pip" install --quiet -e "$REPO[app]" || \
    echo "(the window's GUI toolkit did not install — the browser will be used)"
  touch "$STAMP"
fi

echo
"$VENV/bin/python" -m buspirate ports || true

# `buspirate app` has no --host or --no-browser (the window always binds
# loopback, and there is no browser step to skip), so those two would make
# argparse reject the command before it ever tried to open a window. Strip
# them for the window attempt; the original "$@" still goes to the browser
# fallback below, which does understand both.
app_args=()
skip_next=0
for arg in "$@"; do
  if [ "$skip_next" = 1 ]; then
    skip_next=0
    continue
  fi
  case "$arg" in
    --host)
      skip_next=1
      ;;
    --host=*)
      ;;
    --no-browser)
      ;;
    *)
      app_args+=("$arg")
      ;;
  esac
done

echo
echo "Opening the Bus Pirate window. Close it to stop."
# Exit code 3 is buspirate/cli.py's EXIT_NO_GUI: no usable GUI toolkit, and
# nothing else. Only that is worth retrying in a browser. Anything else — a
# busy port, a bad argument — already printed its own message, and running
# `dashboard` on the same port would just fail again, more confusingly.
"$VENV/bin/python" -m buspirate app "${app_args[@]+"${app_args[@]}"}"
status=$?
if [ "$status" = 3 ]; then
  echo
  echo "No window toolkit available — falling back to the browser dashboard."
  exec "$VENV/bin/python" -m buspirate dashboard "$@"
fi
exit "$status"
