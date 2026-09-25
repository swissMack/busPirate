"""The panel registry — how the dashboard is extended.

A panel declares what it can do; the frontend renders the forms from that
declaration. Adding a protocol therefore means adding one mode class to the
driver and one module to :mod:`buspirate.web.panels`, and touching no
JavaScript at all.

    PANEL = Panel(
        id="mybus",
        title="My bus",
        blurb="One line saying what this is for.",
        mode="mybus",                      # BusPirate.mybus() enters it
        wiring=[Wire("CLK", "red", "SCL")],
        actions=[
            Action(
                name="ping",
                label="Ping",
                help="Says hello to the target.",
                params=[Param("address", "hex", "Address", default=0x50)],
                handler=lambda ctx, address: text(f"pinged {address:#04x}"),
            ),
        ],
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------

#: Parameter types the frontend knows how to render.
PARAM_TYPES = ("int", "hex", "bytes", "bool", "enum", "text", "filename")


@dataclass
class Param:
    """One input on an action's form."""

    name: str
    type: str
    label: str
    default: Any = None
    help: str = ""
    choices: Optional[List[Dict[str, Any]]] = None  # [{"value": .., "label": ..}]
    minimum: Optional[int] = None
    maximum: Optional[int] = None
    placeholder: str = ""

    def __post_init__(self) -> None:
        if self.type not in PARAM_TYPES:
            raise ValueError(f"{self.name}: unknown param type {self.type!r}")
        if self.type == "enum" and not self.choices:
            raise ValueError(f"{self.name}: an enum param needs choices")

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "label": self.label,
            "default": self.default,
            "help": self.help,
            "choices": self.choices,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "placeholder": self.placeholder,
        }


@dataclass
class Action:
    """One button, its form, and the code behind it."""

    name: str
    label: str
    handler: Callable[..., Any]
    help: str = ""
    params: List[Param] = field(default_factory=list)
    #: Capability this needs, e.g. ``"pullup_voltage_select"``. Actions whose
    #: capability the connected device lacks are not offered at all.
    requires: Optional[str] = None
    #: Recipes appear in the one-click strip as well as in their panel.
    recipe: bool = False
    #: Shown as the prominent button in the panel.
    primary: bool = False
    #: Non-empty text asks the user to confirm first.
    confirm: str = ""
    #: Long jobs report progress over the websocket.
    long_running: bool = False
    #: Streaming actions take the port over until stopped: sniffers, bridges,
    #: continuous measurement. They return :func:`live`.
    stream: bool = False
    #: True for actions that must still work while a stream holds the port —
    #: connecting and disconnecting, which end the stream themselves.
    allow_while_streaming: bool = False
    #: True to suppress the automatic form/button the frontend would
    #: otherwise build for this action. The action still runs over
    #: ``/api/run`` — only its generic rendering is skipped, for actions a
    #: panel drives some other way (e.g. a console input row bound to a
    #: live stream rather than a standalone button).
    hidden: bool = False
    #: Names a status field this action flips, and makes the frontend draw it
    #: as one button that shows that state and changes it in a click — the
    #: supplies switch. Its handler takes a single ``on`` parameter.
    switch: str = ""
    #: The button's text, when it should differ from the card's title.
    button: str = ""

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "help": self.help,
            "params": [p.to_json() for p in self.params],
            "requires": self.requires,
            "recipe": self.recipe,
            "primary": self.primary,
            "confirm": self.confirm,
            "long_running": self.long_running,
            "stream": self.stream,
            "allow_while_streaming": self.allow_while_streaming,
            "hidden": self.hidden,
            "switch": self.switch,
            "button": self.button,
        }


@dataclass
class Wire:
    """One row of the wiring block: which probe wire goes where."""

    signal: str
    colour: str
    target: str
    note: str = ""

    def to_json(self) -> dict:
        return {
            "signal": self.signal,
            "colour": self.colour,
            "target": self.target,
            "note": self.note,
        }


@dataclass
class Panel:
    """A tab in the dashboard."""

    id: str
    title: str
    blurb: str
    actions: List[Action]
    #: Name of the :class:`~buspirate.base.BusPirate` method that enters the
    #: protocol mode, or ``None`` for panels that work in bitbang mode.
    mode: Optional[str] = None
    wiring: List[Wire] = field(default_factory=list)
    order: int = 50
    #: Shown under the wiring block; the place for per-protocol warnings.
    notes: List[str] = field(default_factory=list)
    #: Name of the page in ``docs/`` that explains this panel in full.
    doc: Optional[str] = None
    #: Column to highlight on the Bus Pirate reference card, when there is one.
    refcard_column: Optional[str] = None
    #: Extra reference-card rows worth highlighting for this bus.
    refcard_rows: List[str] = field(default_factory=list)

    def action(self, name: str) -> Action:
        for action in self.actions:
            if action.name == name:
                return action
        raise KeyError(f"panel {self.id!r} has no action {name!r}")

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "blurb": self.blurb,
            "mode": self.mode,
            "wiring": [w.to_json() for w in self.wiring],
            "notes": self.notes,
            "doc": self.doc,
            "refcard_column": self.refcard_column,
            "refcard_rows": self.refcard_rows,
            "actions": [a.to_json() for a in self.actions],
        }


# ---------------------------------------------------------------------------
# Results — what a handler returns, and how the frontend draws it
# ---------------------------------------------------------------------------


def text(message: str, *, tone: str = "info") -> dict:
    """A sentence. ``tone`` is ``info``, ``good`` or ``warn``."""
    return {"render": "text", "text": message, "tone": tone}


def hexdump(data: bytes, *, start: int = 0, caption: str = "") -> dict:
    """A hex + ASCII dump."""
    return {
        "render": "hex",
        "data": list(bytes(data)),
        "start": start,
        "caption": caption,
    }


def table(columns: List[str], rows: List[List[Any]], *, caption: str = "") -> dict:
    return {"render": "table", "columns": columns, "rows": rows, "caption": caption}


def chips(items: List[Dict[str, Any]], *, caption: str = "") -> dict:
    """Small labelled tiles — used for I2C scan results."""
    return {"render": "chips", "items": items, "caption": caption}


def keyvalue(pairs: List[List[Any]], *, caption: str = "") -> dict:
    return {"render": "kv", "pairs": pairs, "caption": caption}


def pins(state: Dict[str, bool]) -> dict:
    return {"render": "pins", "state": state}


def live(kind: str, *, decoder: str, caption: str = "", warning: str = "",
         input: bool = False) -> dict:
    """A live stream: the device now talks until it is told to stop.

    ``decoder`` names an entry in :mod:`buspirate.web.decoders`.
    ``input`` marks a stream that accepts typed lines back, which is what
    makes the pane render a console rather than a transcript.
    """
    return {
        "render": "stream",
        "kind": kind,
        "decoder": decoder,
        "caption": caption,
        "warning": warning,
        "input": input,
    }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_panels() -> List[Panel]:
    """Import every module in :mod:`buspirate.web.panels` and collect PANELs."""
    import importlib
    import pkgutil

    from . import panels as panels_package

    found: List[Panel] = []
    for info in pkgutil.iter_modules(panels_package.__path__):
        module = importlib.import_module(f"{panels_package.__name__}.{info.name}")
        panel = getattr(module, "PANEL", None)
        if panel is not None:
            found.append(panel)
    found.sort(key=lambda p: (p.order, p.title))
    return found
