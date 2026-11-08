"""Panels for the boards' own command-line modes, built from their data.

Every :class:`~buspirate.boards._modes.CliMode` of every board in
:data:`buspirate.boards.REGISTRY` becomes one panel, shown only on the board
that has it (its ``cli_mode:<id>`` capability). Each command becomes one
action through :func:`action_for`, which the I2C and UART panels use too for
the Bit Pirate's extra commands, so the two can never differ.
"""

from __future__ import annotations

import contextlib

import string
from typing import Any, Dict, List, Optional

from ... import boards
from ...boards._modes import CliCommand, CliMode, CliParam, cli_mode_capability
from ...capabilities import CAP_CLI_EXTRAS
from ..params import ParamError
from ..registry import Action, Panel, Param, Wire, lines, live

#: After UART (40), before the Bus Pirate's 1-Wire (50).
FIRST_ORDER = 41


def _word(param: CliParam, value: Any) -> str:
    """One value as the firmware wants it on its command line."""
    if param.type == "hex":
        return f"0x{value:02X}"
    if param.type != "text":
        return str(value)
    text = str(value).strip()
    if not text:
        raise ParamError(f"{param.label}: needs a value")
    if not all(" " <= c <= "~" for c in text):
        raise ParamError(f"{param.label}: plain letters, digits and punctuation only")
    if not param.spaces and " " in text:
        raise ParamError(f"{param.label}: cannot contain spaces")
    return text


def _param(p: CliParam) -> Param:
    return Param(p.name, p.type, p.label, default=p.default, help=p.help,
                 choices=p.choices, minimum=p.minimum, maximum=p.maximum, secret=p.secret,
                 shown_when=dict([p.shown_when]) if p.shown_when else None)


def action_for(cmd: CliCommand, requires: Optional[str] = None) -> Action:
    """The button for one command: fill in its line, run it, show the reply."""
    by_name = {p.name: p for p in cmd.params}
    by_value = dict(cmd.lines)

    def template(values: Dict[str, Any]) -> str:
        if cmd.choose_by:
            return by_value.get(values.get(cmd.choose_by), cmd.line)
        return cmd.line

    def used(values: Dict[str, Any]) -> List[str]:
        return [n for _, n, _, _ in string.Formatter().parse(template(values)) if n]

    def words(values: Dict[str, Any], mask: bool = False) -> str:
        # Only the fields this line uses: a hidden box (the new network's
        # name, while the saved one is chosen) is neither checked nor sent.
        return template(values).format(**{
            name: "****" if mask and by_name[name].secret else _word(by_name[name], values[name])
            for name in used(values)
        })

    def explain(said: List[str]) -> None:
        for phrase, message in cmd.explains:
            if any(phrase in said_line for said_line in said):
                raise ParamError(message)

    def restart(ctx, line: str):
        said, gone = ctx.mode.run_restarting(line, timeout=cmd.timeout)
        ctx.session.note_reply(said)
        explain(said)
        if not any(cmd.restarts in said_line for said_line in said):
            raise ParamError(cmd.refuses)
        ready = ctx.session.left_for_web_cli()
        info = ctx.session.web_cli or {}
        if ready:
            said.append(f"The Web CLI is ready at http://{info['ip']}")
        elif info.get("ip"):
            said.append(f"The Web CLI did not answer at http://{info['ip']} yet. "
                        "Wait a little, then open it; reset the board to come back to USB.")
        return lines(said, caption=f"The board's reply to '{line}'")

    def handler(ctx, **values):
        line, shown = words(values), words(values, mask=True)
        if cmd.restarts:
            return restart(ctx, line)
        if cmd.streams:
            ctx.mode.start_stream(line)
            return live(cmd.label, decoder="console",
                        caption="What the board prints, as it prints it. Stop ends it.")
        secret = any(by_name[name].secret for name in used(values))
        try:
            with ctx.session.traffic_hidden(shown) if secret else contextlib.nullcontext():
                said = ctx.mode.run(line, timeout=cmd.timeout, shown=shown,
                                    picks=list(cmd.picks) or None)
            ctx.session.note_reply(said)
            explain(said)
        finally:
            # Even a stopped command may have changed them (autobaud leaves
            # the UART at the last rate it tried).
            if cmd.forgets:
                ctx.mode.forget(cmd.forgets)
        return lines(said, caption=f"The board's reply to '{shown}'")

    return Action(
        name=cmd.name,
        label=cmd.label,
        help=cmd.help,
        params=[_param(p) for p in cmd.params],
        requires=requires,
        stream=cmd.streams,
        handler=handler,
        check=words if cmd.params else None,
    )


def _wiring(mode: CliMode) -> List[Wire]:
    if not mode.wires:
        return []
    rows = [Wire("GND", "", "GND", "always connect this first")]
    rows += [Wire(signal, "", target, note) for signal, target, note in mode.wires]
    rows.append(Wire("VIO", "", "VCC", "the voltage set on the dock's slide switch"))
    return rows


def panel_for(mode: CliMode, order: int) -> Panel:
    return Panel(
        id=mode.id,
        title=mode.title,
        blurb=mode.blurb,
        mode=f"cli:{mode.id}",
        doc=mode.doc,
        order=order,
        group=mode.group,
        requires=cli_mode_capability(mode.id),
        wiring=_wiring(mode),
        notes=[mode.needs] if mode.needs else [],
        actions=[action_for(cmd) for cmd in mode.commands],
    )


def extra_actions(panel_id: str) -> List[Action]:
    """The board-only extra commands for one of the shared panels."""
    from ...boards.bitpirate_modes import EXTRA_ACTIONS

    return [action_for(cmd, requires=CAP_CLI_EXTRAS) for cmd in EXTRA_ACTIONS.get(panel_id, ())]


def _all_modes() -> List[CliMode]:
    seen, found = set(), []
    for board in boards.REGISTRY.values():
        for mode in board.modes:
            if mode.id not in seen:
                seen.add(mode.id)
                found.append(mode)
    return found


PANELS = [panel_for(mode, FIRST_ORDER + index) for index, mode in enumerate(_all_modes())]
