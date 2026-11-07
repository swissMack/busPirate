"""A board's own command-line modes, described as data.

A :class:`CliMode` is one mode of a text-command-line board (the ESP32 Bit
Pirate): what to type after ``m``, the answers to its ``config`` pin
questions, and the commands it offers. The web app turns each one into a
panel (``web/panels/cli_modes.py``) and the driver enters it generically
(``bitpirate.modes.CliModeSession``), so adding a mode is adding data here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CliParam:
    """One field of a command: becomes a panel field, then a word of the line."""

    name: str
    #: One of web.registry.PARAM_TYPES.
    type: str
    label: str
    default: Any = None
    choices: Optional[List[Dict[str, Any]]] = None
    minimum: Optional[int] = None
    maximum: Optional[int] = None
    help: str = ""
    #: False for a word the firmware splits on spaces (a Wi-Fi password).
    spaces: bool = True
    #: Never shown back: replaced by **** in captions and errors.
    secret: bool = False
    #: (field, value): shown, and used, only while that field has that value.
    shown_when: Optional[Tuple[str, str]] = None


@dataclass(frozen=True)
class CliCommand:
    """One command: a button in the panel, one line typed at the prompt."""

    name: str
    label: str
    #: A str.format template over the params' names, e.g. "pwm {pin} {freq} {duty}".
    line: str
    params: Tuple[CliParam, ...] = ()
    #: Runs until Enter: the panel shows it live instead of waiting for a reply.
    streams: bool = False
    #: Seconds to wait for the prompt to come back.
    timeout: float = 5.0
    help: str = ""
    #: Config answers (by question label) the command changes on the board,
    #: so the driver's record of them is dropped afterwards.
    forgets: Tuple[str, ...] = ()
    #: Menu items to pick, by label, should the firmware show a menu.
    picks: Tuple[str, ...] = ()
    #: (words in the reply, what to say instead): a reply holding those words
    #: is refused with the plain message, e.g. a connect with nothing saved.
    explains: Tuple[Tuple[str, str], ...] = ()
    #: A choice of lines: the value of the field ``choose_by`` picks one of
    #: ``lines`` ((value, line), ...); ``line`` is used for any other value.
    choose_by: str = ""
    lines: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CliMode:
    """One firmware mode, and the commands the menu offers in it."""

    #: The panel id; unique across every panel.
    id: str
    title: str
    #: What follows ``m`` on the command line, e.g. "1wire".
    cli_name: str
    #: The menu heading it sits under: "Buses" or "Wireless".
    group: str
    blurb: str
    #: Its guide page.
    doc: str
    commands: Tuple[CliCommand, ...]
    #: Answers to its config questions, by question label.
    pins: Dict[str, str] = field(default_factory=dict)
    #: A line on extra hardware it needs; empty when none.
    needs: str = ""
    #: Its wiring rows on the dock header, as (signal, target, note); the
    #: panel adds GND before and VIO after. Empty for a radio mode.
    wires: Tuple[Tuple[str, str, str], ...] = ()
    #: Lines that let go of every pin it may have driven, run in this mode
    #: on HiZ and on disconnect when it was used: the firmware's own
    #: ``m hiz`` leaves some modes' outputs (DIO's levels, PWM) running.
    release: Tuple[str, ...] = ()


def cli_mode_capability(mode_id: str) -> str:
    """The capability that shows a mode's panel: only its board has it."""
    return f"cli_mode:{mode_id}"
