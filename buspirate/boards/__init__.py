"""Every board the app supports, each described once.

One module per board holds a single :class:`Board`. Everything else — the
device profile, the dashboard's wiring and LEDs, the guide — reads it from
:data:`REGISTRY` rather than keeping its own per-board table. Adding a
board means adding its module and its line below.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Optional

from ..capabilities import BUS_PIRATE_ONLY, CAP_ADC, CAP_FREQUENCY, CAP_PWM
from . import bitpirate, bp6, v3, v4
from ._board import Board

#: By variant, in the order menus list them.
REGISTRY: Dict[str, Board] = {
    board.variant: board for board in (v3.BOARD, v4.BOARD, bitpirate.BOARD, bp6.BOARD)
}

#: What to present when nothing is connected, or the banner was unreadable.
DEFAULT_VARIANT = "v3"

#: An unidentified Bus Pirate: only what every documented variant shares.
UNKNOWN_CAPABILITIES: FrozenSet[str] = BUS_PIRATE_ONLY | frozenset(
    {CAP_PWM, CAP_ADC, CAP_FREQUENCY}
)


def get(variant: Optional[str]) -> Board:
    """The board for ``variant``, or the default board if there is none."""
    return REGISTRY.get(variant or "", REGISTRY[DEFAULT_VARIANT])


def capabilities_for(variant: str) -> FrozenSet[str]:
    board = REGISTRY.get(variant)
    return board.capabilities if board is not None else UNKNOWN_CAPABILITIES


__all__ = ["Board", "REGISTRY", "DEFAULT_VARIANT", "UNKNOWN_CAPABILITIES", "get",
           "capabilities_for"]
