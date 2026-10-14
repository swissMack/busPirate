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
