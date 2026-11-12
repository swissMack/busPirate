"""Recipes: one entry per use case — the wiring, the power, a check and an action.

Each bus module in this package registers its recipes with ``register``; the
engine (``buspirate.mcp_bp6.engine``) plans and runs them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...mcp.wiring import JOBS

RISKS = ("none", "destructive", "owner-only")
BUSES = JOBS + ("led", "jtag", "board", "infrared")
TRANSPORTS = ("bpio2", "terminal")
SUPPLIED_BY = ("engine", "action")

#: Planks: an adapter that plugs into the main header in place of loose wires. A recipe
#: with ``plank`` set shows the plank's ``setup`` steps (and its ``notes``) as its wiring.
PLANKS = {
    "sim-iccard": {
        "name": "IC card and SIM adapter plank",
        "setup": (
            "plug the plank into the Bus Pirate's main header",
            "set the switches to VCC:VOUT and GND:GND",
            "put the card in the mini, micro or nano SIM socket (or a smart card in the "
            "socket on the back)",
        ),
        "notes": (
            "the CARD LED lights only for a card in the large socket on the back; a SIM in "
            "the nano, micro or mini socket leaves it dark — the power LED shows the card "
            "is powered",
        ),
        "source": "https://docs.buspirate.com/docs/overview/sim-iccard-adapter/",
    },
}  # type: Dict[str, Dict[str, Any]]


@dataclass(frozen=True)
class Recipe:
    """A use case. ``check`` and ``action`` take the board and the merged options.

    ``check`` returns ``{"ok": False, ...}`` to stop before the action. A
    recipe whose ``max_mv`` is 0 needs no supply at all. ``default_mv`` 0 means
    there is no safe default: the owner must state the voltage.

    A destructive recipe's ``action`` only prepares (it never writes) and
    returns the public keys ``chip``, ``operation``, ``start``, ``length``,
    ``summary`` and ``backup`` plus private keys starting with ``_``;
    ``commit(bp, options, prepared)`` makes the change.

    A ``transport="terminal"`` recipe runs in the board's text terminal: its
    ``check`` and ``action`` get the ``Console`` in place of the board. The
    engine first switches to ``terminal_mode`` (the ``m`` argument; None stays
    in HiZ), adding ``terminal_flags`` (the rest of the ``m`` line, such as
    ``-s 400``), then applies the planned supply (unless ``supply_by="action"``,
    when the firmware's own prompt sets it) and the pull-ups. ``precheck``,
    if given, runs over BPIO2 with the board before the terminal opens. A
    recipe with ``target_powered_ok`` False refuses a target that has its own
    supply, giving ``target_powered_error`` as the reason when it is set. A
    destructive terminal recipe's ``commit`` gets the ``Console`` too, and runs
    only while the terminal is still in ``terminal_mode``.

    ``change_lines`` are the starts of the terminal lines that make the change
    (``"rm "``, ``"usbpd request"``). The engine marks the commit as sent the
    moment one goes out; a trip or an error after that point is reported as
    ``committed: None`` with ``may_have_changed`` and ``change_hint`` (what the
    owner should do to find out), never as a plain "not committed". A terminal
    commit with no ``change_lines`` counts as sent as soon as ``commit`` runs.
    """

    name: str
    title: str
    words: Tuple[str, ...]
    bus: str
    default_mv: int
    min_mv: int
    max_mv: int
    pullups: bool
    wiring: Tuple[Tuple[str, str], ...]  # (target pin, BP6 pin such as "IO0" or "VOUT")
    check: Callable[[Any, Dict[str, Any]], Dict[str, Any]]
    action: Callable[[Any, Dict[str, Any]], Dict[str, Any]]
    options: Dict[str, Any]
    source: str  # the docs.buspirate.com page it comes from
    milliamps: int = 100
    risk: str = "none"
    notes: Tuple[str, ...] = ()
    commit: Optional[Callable[[Any, Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None
    transport: str = "bpio2"
    terminal_mode: Optional[str] = None
    terminal_flags: str = ""
    precheck: Optional[Callable[[Any, Dict[str, Any]], Dict[str, Any]]] = None
    supply_by: str = "engine"
    target_powered_ok: bool = True
    target_powered_error: str = ""
    #: Given the merged options, the wiring to show in place of ``wiring`` (a recipe
    #: whose pins depend on an option, such as which IR sensor is used).
    wiring_for: Optional[Callable[[Dict[str, Any]], Tuple[Tuple[str, str], ...]]] = None
    change_lines: Tuple[str, ...] = ()
    change_hint: str = ""
    #: Set by a recipe whose options hold a secret (a PIN): why ``recipe_run(token=None)``
    #: refuses it. The engine then keeps none of its options after a run or a commit.
    no_rerun: str = ""
    #: A key of ``PLANKS``: the recipe runs on that plank, and its plan shows the plank's
    #: setup steps in place of the per-wire ``wiring`` (which still names the pins used).
    plank: Optional[str] = None

    def __post_init__(self) -> None:
        if self.plank is not None and self.plank not in PLANKS:
            raise ValueError("recipe %r: plank must be one of %s" % (self.name, sorted(PLANKS)))
        if self.bus not in BUSES:
            raise ValueError("recipe %r: bus must be one of %s" % (self.name, BUSES))
        if self.risk not in RISKS:
            raise ValueError("recipe %r: risk must be one of %s" % (self.name, RISKS))
        if not self.min_mv <= self.max_mv:
            raise ValueError("recipe %r: min_mv is above max_mv" % self.name)
        if self.default_mv and not self.min_mv <= self.default_mv <= self.max_mv:
            raise ValueError("recipe %r: default_mv is outside min_mv..max_mv" % self.name)
        if (self.risk == "destructive") != (self.commit is not None):
            raise ValueError("recipe %r: a destructive recipe needs a commit, and only a "
                             "destructive recipe has one" % self.name)
        if self.transport not in TRANSPORTS:
            raise ValueError("recipe %r: transport must be one of %s" % (self.name, TRANSPORTS))
        if self.supply_by not in SUPPLIED_BY:
            raise ValueError("recipe %r: supply_by must be one of %s" % (self.name, SUPPLIED_BY))
        if self.transport != "terminal" and (self.terminal_mode or self.precheck
                                             or self.terminal_flags or self.supply_by != "engine"):
            raise ValueError("recipe %r: terminal_mode, terminal_flags, precheck and supply_by are for "
                             "terminal recipes" % self.name)


REGISTRY = {}  # type: Dict[str, Recipe]


def register(recipe: Recipe) -> Recipe:
    if recipe.name in REGISTRY:
        raise ValueError("a recipe named %r is already registered" % recipe.name)
    REGISTRY[recipe.name] = recipe
    return recipe


def _plank_words(recipe: Recipe) -> List[str]:
    """The plank's key, its name and the word "plank"."""
    if recipe.plank is None:
        return []
    return [recipe.plank.lower(), PLANKS[recipe.plank]["name"].lower(), "plank"]


def _rank_one(recipe: Recipe, query: str) -> Optional[int]:
    """0 exact name, 1 one of its words, 2 a substring of name, words or title.

    The words include the plank's (``_plank_words``), so "plank" finds a plank's recipes.
    """
    if recipe.name.lower() == query:
        return 0
    words = [w.lower() for w in recipe.words] + _plank_words(recipe)
    if query in words:
        return 1
    if any(query in text for text in [recipe.name.lower(), recipe.title.lower()] + words):
        return 2
    return None


def _rank(recipe: Recipe, query: str) -> Optional[int]:
    """The whole query's rank; failing that, a query of several words matches when every
    word does, ranked by its worst word ("sim plank")."""
    rank = _rank_one(recipe, query)
    terms = query.split()
    if rank is not None or len(terms) < 2:
        return rank
    ranks = [_rank_one(recipe, term) for term in terms]
    if any(r is None for r in ranks):
        return None
    return 2 + max(ranks)  # type: ignore[operator]


def find_recipes(query: Optional[str]) -> List[Dict[str, Any]]:
    """Recipes matching ``query``, best first; with no query, all of them by bus."""
    q = (query or "").strip().lower()
    if not q:
        found = sorted(REGISTRY.values(), key=lambda r: (r.bus, r.name))
    else:
        ranked = [(rank, r.name, r) for r in REGISTRY.values()
                  for rank in [_rank(r, q)] if rank is not None]
        found = [r for _, _, r in sorted(ranked, key=lambda item: item[:2])]
    return [{"name": r.name, "title": r.title, "bus": r.bus, "source": r.source,
             "plank": PLANKS[r.plank]["name"] if r.plank else None}
            for r in found]


from . import i2c  # noqa: E402,F401  (registers the I2C recipes)
from . import board, ddr, disk, handoff, identify, jtag, led, infrared, onewire, pins, signals, sim, sniff, smartcard, spi, uart, usbpd  # noqa: E402,F401  (the other buses)
