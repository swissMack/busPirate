import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buspirate import BusPirate  # noqa: E402
from tests.fake_serial import FakeSerial, fake_factory  # noqa: E402


def make_device(fake, **kwargs):
    """A BusPirate wired to ``fake``, with identification made test-fast."""
    kwargs.setdefault("identify_timeout", 0.02)
    return BusPirate("/dev/fake", serial_factory=fake_factory(fake), **kwargs)


@pytest.fixture(params=["v3", "v4"])
def variant(request):
    """Runs the mode tests once as a Bus Pirate v3 and once as a v4."""
    return request.param


@pytest.fixture
def fake(variant):
    return FakeSerial(variant=variant)


@pytest.fixture
def bp(fake):
    device = make_device(fake)
    with device:
        yield device
