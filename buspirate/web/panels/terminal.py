"""The Bus Pirate's own text terminal — opened, typed into, and left.

Kept as its own panel (rather than living on Connection) so starting,
typing and stopping the console are one group in one place: the pane that
`open_terminal` starts stays reachable by coming back to this panel, and
`send_keys` is grouped right next to the action that opens the session it
feeds.
"""

from __future__ import annotations

from ..registry import Action, Panel, Param, text


def _open_terminal(ctx):
    return ctx.session.enter_terminal()


def _send_keys(ctx, keys):
    ctx.session.send_terminal_keys(keys)
    return text(f"Sent {keys!r}.")


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
            confirm="This leaves binary mode, which resets the board — a v3 "
            "and a v4 alike: the supplies go off and the pins go to inputs. A "
            "v4 also drops off USB for a moment and is reconnected. Nothing is "
            "restored when you come back. Continue?",
            stream=True,
            handler=_open_terminal,
        ),
        Action(
            name="send_keys",
            label="Send",
            help="Types keys into the board's terminal, exactly as given — "
            "Enter is a \\r of its own, never added.",
            params=[Param("keys", "text", "Keys", default="")],
            allow_while_streaming=True,
            # The console input row on the live pane calls this action
            # directly — it needs no button/form of its own, and showing one
            # anyway was the third half of the bug this panel fixes.
            hidden=True,
            handler=_send_keys,
        ),
    ],
)
