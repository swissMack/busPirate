"""The simulator moved into the package as ``buspirate.simulator`` so the
dashboard can offer it at runtime; this keeps the tests' imports working."""

from buspirate.simulator import BANNERS, FakeFlash, FakeSerial, fake_factory

__all__ = ["BANNERS", "FakeFlash", "FakeSerial", "fake_factory"]
