#!/bin/bash
# Build the distributable Bus Pirate app and its disk image.
#
#   bin/build-dmg.sh
#
# Produces:
#   dist/BusPirate.app                    — self-contained, needs no Python
#   dist/BusPirate-<version>-arm64.dmg    — attach this to a GitHub release
#
# This is NOT bin/BusPirate.app. That one is a thin shim for working in the
# checkout: it runs bin/dashboard.command against the repo's .venv. This
# script freezes the whole dashboard — interpreter, FastAPI, pywebview, the
# static frontend and docs/ — into a bundle that runs on a Mac with nothing
# installed.
#
# Apple Silicon only, and deliberately unsigned: the only certificate on hand
# is an Apple Development one, which cannot sign for distribution and would
# produce something that looks signed and still refuses to open. PyInstaller
# ad-hoc signs the bundle, which is the minimum arm64 needs to execute at
# all; this script checks that it did. Downloaders right-click → Open once.

set -euo pipefail

REPO="$(cd -P "$(dirname "$0")/.." && pwd)"
cd "$REPO"

BUILD_VENV="$REPO/build/dmg-venv"
DIST="$REPO/dist"
APP="$DIST/BusPirate.app"

# The version is pyproject.toml's, never a second copy to keep in step.
VERSION="$(sed -n 's/^version *= *"\(.*\)"/\1/p' pyproject.toml | head -1)"
if [ -z "$VERSION" ]; then
  echo "could not read version from pyproject.toml" >&2
  exit 1
fi
DMG="$DIST/BusPirate-$VERSION-arm64.dmg"

if [ "$(uname -m)" != "arm64" ]; then
  echo "this builds an arm64-only app and must run on Apple Silicon" >&2
  exit 1
fi

echo "==> Bus Pirate $VERSION (arm64)"

# A build environment of its own. The repo's .venv is the dev environment and
# is deliberately left alone — the whole point of the built app is that it
# does not need it, so it must not be part of building it either.
if [ ! -x "$BUILD_VENV/bin/python" ]; then
  echo "==> creating the build environment in build/dmg-venv"
  python3 -m venv "$BUILD_VENV"
fi
echo "==> installing build dependencies"
"$BUILD_VENV/bin/pip" install --quiet --upgrade pip
"$BUILD_VENV/bin/pip" install --quiet "pyinstaller>=6.6" ".[web,app]"

echo "==> freezing"
rm -rf "$APP" "$DIST/BusPirate" "$REPO/build/BusPirate"
BUSPIRATE_REPO="$REPO" BUSPIRATE_VERSION="$VERSION" \
  "$BUILD_VENV/bin/pyinstaller" \
    --noconfirm \
    --distpath "$DIST" \
    --workpath "$REPO/build" \
    "$REPO/packaging/BusPirate.spec"

# PyInstaller leaves the plain COLLECT directory next to the bundle. It is the
# same payload twice; only the .app ships.
rm -rf "$DIST/BusPirate"

# --- checks on the bundle itself -------------------------------------------
# Each of these is a way the bundle has actually been seen to come out wrong,
# so they are checked rather than assumed.

fail=0
check() {  # check <description> <path-inside-Contents>
  if [ -e "$APP/Contents/$2" ]; then
    echo "    ok   $1"
  else
    echo "    MISSING  $1  ($2)" >&2
    fail=1
  fi
}

echo "==> checking the bundle"
check "frontend (static/)" "Frameworks/buspirate/web/static/index.html"
check "board photos"       "Frameworks/buspirate/web/static/img/board-v3.png"
check "Bit Pirate drawing" "Frameworks/buspirate/web/static/img/board-bitpirate.svg"
check "Bit Pirate guide"   "Frameworks/docs/bitpirate.md"
check "guide (docs/)"      "Frameworks/docs/user-guide.md"
check "executable"         "MacOS/BusPirate"

# arm64 refuses to execute an unsigned binary at all, so the ad-hoc signature
# PyInstaller applies is load-bearing, not cosmetic. Check that it is *valid*,
# not just present: PyInstaller's signing can fail halfway and leave a
# signature behind that codesign then rejects.
if codesign -v "$APP" 2>/dev/null; then
  echo "    ok   ad-hoc signature valid"
else
  echo "    WARNING: signature missing or invalid — re-signing" >&2
  # A checkout under ~/Documents is synced by iCloud, which stamps Finder
  # and file-provider attributes on the fresh bundle — and re-stamps them
  # as fast as xattr can strip them — so codesign refuses the "detritus".
  # Sign a copy somewhere iCloud does not reach, then bring it back: the
  # attributes iCloud adds afterwards do not invalidate a finished signature.
  SIGN_DIR="$(mktemp -d)"
  ditto --noextattr --noqtn "$APP" "$SIGN_DIR/BusPirate.app"
  xattr -cr "$SIGN_DIR/BusPirate.app"
  codesign --force --deep --sign - "$SIGN_DIR/BusPirate.app"
  rm -rf "$APP"
  ditto "$SIGN_DIR/BusPirate.app" "$APP"
  rm -rf "$SIGN_DIR"
  if codesign -v "$APP"; then
    echo "    ok   ad-hoc signature valid"
  else
    echo "    signing failed" >&2
    fail=1
  fi
fi

[ "$fail" = 0 ] || { echo "bundle is incomplete" >&2; exit 1; }

# --- disk image -------------------------------------------------------------
# hdiutil only; no create-dmg dependency. A staging directory keeps the image
# to the app plus an /Applications alias to drag it onto.
echo "==> building $(basename "$DMG")"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create \
  -volname "Bus Pirate $VERSION" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "$DMG" >/dev/null

echo
echo "built:"
echo "  $APP"
echo "  $DMG  ($(du -h "$DMG" | cut -f1))"
echo
echo "The app is unsigned and not notarized. First launch: right-click it in"
echo "Finder and choose Open, or use System Settings → Privacy & Security →"
echo "Open Anyway. Double-clicking it the first time will be refused."
