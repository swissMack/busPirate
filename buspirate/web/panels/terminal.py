"""The Bus Pirate's own text terminal — opened, typed into, and left.

Kept as its own panel (rather than living on Connection) so starting,
typing and stopping the console are one group in one place: the pane that
`open_terminal` starts stays reachable by coming back to this panel, and
`send_line` is grouped right next to the action that opens the session it
feeds.
"""

from __future__ import annotations

from ..registry import Action, Panel, Param, text


def _open_terminal(ctx):
    return ctx.session.enter_terminal()


def _send_line(ctx, line):
    ctx.session.send_terminal_line(line)
    return text(f"Sent {line!r}.")


PANEL = Panel(
    id="terminal",
    title="Terminal",
    blurb="The Bus Pirate's own command prompt — the `HiZ>` console, not the binary protocol.",
    mode=None,
    order=15,
    actions=[
        Action(
            name="open_terminal",
            label="Open the board's terminal",
            help="Leaves binary mode and gives you the Bus Pirate's own "
            "command prompt. Everything else in the dashboard is unavailable "
            "until you close it.",
            confirm="This leaves binary mode. On a Bus Pirate v3 that resets "
            "the board: the supplies go off and the pins go to inputs. On a v4 "
            "the board is not reset, but the current protocol mode is dropped. "
            "Nothing is restored when you come back. Continue?",
            stream=True,
            handler=_open_terminal,
        ),
        Action(
            name="send_line",
            label="Send",
            help="Types one line into the board's terminal.",
            params=[Param("line", "text", "Command", default="")],
            allow_while_streaming=True,
            # The console input row on the live pane calls this action
            # directly — it needs no button/form of its own, and showing one
            # anyway was the third half of the bug this panel fixes.
            hidden=True,
            handler=_send_line,
        ),
    ],
)
