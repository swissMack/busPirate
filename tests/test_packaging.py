"""The macOS app bundles what the code imports lazily."""

import re
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "packaging" / "BusPirate.spec"


def test_the_bus_pirate_6_modules_are_hidden_imports():
    # connect.py, session.py and device.py import these inside functions, so
    # PyInstaller's analysis cannot see them; a missing one breaks only the app.
    listed = set(re.findall(r'"(buspirate[\w.]*)"', SPEC.read_text()))
    for module in ("buspirate.bp6", "buspirate.bp6.modes", "buspirate.bp6.protocol",
                   "buspirate.simulator_bp6"):
        assert module in listed, module


def test_notes_ship_in_package(tmp_path):
    # Build the real wheel: package-data globs are only proven by building it.
    import subprocess
    import sys
    import zipfile

    import pytest

    root = SPEC.parent.parent
    pytest.importorskip("setuptools")
    done = subprocess.run(
        [sys.executable, "-c",
         "from setuptools import build_meta; build_meta.build_wheel(%r)" % str(tmp_path)],
        capture_output=True, text=True, cwd=str(root),
    )
    if "bdist_wheel" in done.stderr:
        pytest.skip("this environment's setuptools cannot build wheels (no `wheel`)")
    assert done.returncode == 0, done.stderr
    wheel = next(tmp_path.glob("buspirate-*.whl"))
    names = zipfile.ZipFile(str(wheel)).namelist()
    assert "buspirate/mcp/notes/esp.md" in names
    assert "buspirate/mcp/server.py" in names


def test_notes_are_declared_as_package_data():
    # The wheel build above is skipped where `wheel` is missing; this is the
    # part of it that needs no build.
    root = SPEC.parent.parent
    text = (root / "pyproject.toml").read_text()
    assert '"buspirate.mcp" = ["notes/*.md"]' in text
    assert '"buspirate.mcp"' in text.split("packages = [", 1)[1].split("]", 1)[0]
    assert (root / "buspirate" / "mcp" / "notes" / "esp.md").is_file()


def test_mcp_extra_is_optional_and_gated():
    text = (SPEC.parent.parent / "pyproject.toml").read_text()
    assert "mcp>=2.3,<3; python_version >= '3.10'" in text
    assert 'requires-python = ">=3.8"' in text
