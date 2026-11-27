"""What the bp6 server knows about a board beyond the shared ``BoardSession``.

``BoardSession`` is shared with the other servers and gets no new attributes,
so the Bus Pirate 6's own state is kept here, one ``Bp6State`` per session.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set


@dataclass
class Bp6State:
    #: The board while it is lent to another program (a hand-off), else None.
    lent: Optional[Dict[str, Any]] = None
    #: The IO pins the terminal's ``G`` has a PWM running on.
    pwm_pins: Set[int] = field(default_factory=set)
    #: The ``m`` argument the last terminal recipe switched to (None: HiZ, or none ran).
    terminal_mode: Optional[str] = None


_STATES = weakref.WeakKeyDictionary()  # type: weakref.WeakKeyDictionary


def of(session: Any) -> Bp6State:
    """The ``Bp6State`` of ``session``, made on first use."""
    st = _STATES.get(session)
    if st is None:
        st = _STATES[session] = Bp6State()
    return st
