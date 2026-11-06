"""The shape of a board definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional, Tuple

from ._modes import CliMode


@dataclass(frozen=True)
class Board:
    """Everything the app knows about one kind of board, in one place."""

    #: The profile's variant string: "v3", "v4", "bp6" or "bitpirate".
    variant: str
    #: How the board is named everywhere: status bar, menus, errors.
    name: str
    #: What its firmware lets the dashboard do (buspirate.capabilities).
    capabilities: FrozenSet[str]
    #: Its entry in the port list when simulated.
    simulated_name: str
    #: The line shown above its own terminal in the Terminal panel.
    terminal_caption: str
    #: Our guide page about this board, moved up the guide's menu while it is
    #: connected; None when the topic pages already assume this board.
    guide_page: Optional[str]
    #: The folder under docs/ holding the maker's manual for it.
    manual: str
    #: The board picture, pin geometry, per-panel wording and wiring tables.
    wiring: Dict[str, Any] = field(default_factory=dict)
    #: What drives each LED and how its state is inferred (see web.wiring).
    led_rules: Dict[str, Dict[str, str]] = field(default_factory=dict)
    #: The note shown under the LED strip.
    led_note: str = ""
    #: Whether it talks text (a command line), so the Traffic panel can show
    #: what was said rather than hex.
    traffic_text: bool = False
    #: Guide page by panel id, where this board has its own reference for
    #: that job; other panels keep their own page.
    panel_docs: Dict[str, str] = field(default_factory=dict)
    #: Its own command-line modes, each offered as a panel (web/panels/cli_modes.py).
    modes: Tuple[CliMode, ...] = ()
