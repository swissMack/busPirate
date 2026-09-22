# PyInstaller spec for the distributable BusPirate.app.
#
# Run it through bin/build-dmg.sh — that script builds the isolated build
# environment, passes REPO and VERSION in, and wraps the result in a .dmg.
#
# Three paths have to be laid out exactly as they are in a checkout, because
# the code finds them relative to its own __file__ and PyInstaller reproduces
# the package tree under sys._MEIPASS:
#
#   buspirate/web/static  -> web/server.py STATIC_DIR (<package>/static)
#   docs/                 -> web/docs.py   DOCS_DIR   (<package>/../../docs)
#
# Putting them at those names means neither module needs a frozen-only branch.
# (The third trap, captures/, is not a path in the bundle: it is fixed in
# buspirate/web/session.py captures_root().)

import os

from PyInstaller.utils.hooks import collect_submodules

REPO = os.environ["BUSPIRATE_REPO"]
VERSION = os.environ["BUSPIRATE_VERSION"]

datas = [
    (os.path.join(REPO, "buspirate", "web", "static"), "buspirate/web/static"),
    (os.path.join(REPO, "docs"), "docs"),
]

hiddenimports = (
    collect_submodules("buspirate.web.panels")
    + collect_submodules("uvicorn")
    + [
        "webview.platforms.cocoa",
        "serial.tools.list_ports",
    ]
)

a = Analysis(
    [os.path.join(REPO, "packaging", "app_main.py")],
    pathex=[REPO],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BusPirate",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    target_arch="arm64",
    codesign_identity=None,  # ad-hoc only; see bin/build-dmg.sh
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BusPirate",
)

app = BUNDLE(
    coll,
    name="BusPirate.app",
    icon=os.path.join(REPO, "bin", "BusPirate.app", "Contents", "Resources",
                      "BusPirate.icns"),
    bundle_identifier="local.buspirate.app",
    version=VERSION,
    info_plist={
        "CFBundleName": "Bus Pirate",
        "CFBundleDisplayName": "Bus Pirate",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.developer-tools",
        "NSHighResolutionCapable": True,
        # The dashboard talks to its own loopback server.
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    },
)
