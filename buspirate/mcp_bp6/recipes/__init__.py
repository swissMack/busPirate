"""Recipes: one entry per use case — the wiring, the power, a check and an action.

Each bus module in this package registers its recipes with ``register``; the
engine (``buspirate.mcp_bp6.engine``) plans and runs them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...mcp.wiring import JOBS

RISKS = ("none", "destructive", "owner-only")
BUSES = JOBS + ("led",)


@dataclass(frozen=True)
class Recipe:
    """A use case. ``check`` and ``action`` take the board and the merged options.

    ``check`` returns ``{"ok": False, ...}`` to stop before the action. A
    recipe whose ``max_mv`` is 0 needs no supply at all. ``default_mv`` 0 means
    there is no safe default: the owner must state the voltage.
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

    def __post_init__(self) -> None:
        if self.bus not in BUSES:
            raise ValueError("recipe %r: bus must be one of %s" % (self.name, BUSES))
        if self.risk not in RISKS:
            raise ValueError("recipe %r: risk must be one of %s" % (self.name, RISKS))
        if not self.min_mv <= self.max_mv:
            raise ValueError("recipe %r: min_mv is above max_mv" % self.name)
        if self.default_mv and not self.min_mv <= self.default_mv <= self.max_mv:
            raise ValueError("recipe %r: default_mv is outside min_mv..max_mv" % self.name)


REGISTRY = {}  # type: Dict[str, Recipe]


def register(recipe: Recipe) -> Recipe:
    if recipe.name in REGISTRY:
        raise ValueError("a recipe named %r is already registered" % recipe.name)
    REGISTRY[recipe.name] = recipe
    return recipe


def _rank(recipe: Recipe, query: str) -> Optional[int]:
    """0 exact name, 1 one of its words, 2 a substring of name, words or title."""
    if recipe.name.lower() == query:
        return 0
    words = [w.lower() for w in recipe.words]
    if query in words:
        return 1
    if any(query in text for text in [recipe.name.lower(), recipe.title.lower()] + words):
        return 2
    return None


def find_recipes(query: Optional[str]) -> List[Dict[str, str]]:
    """Recipes matching ``query``, best first; with no query, all of them by bus."""
    q = (query or "").strip().lower()
    if not q:
        found = sorted(REGISTRY.values(), key=lambda r: (r.bus, r.name))
    else:
        ranked = [(rank, r.name, r) for r in REGISTRY.values()
                  for rank in [_rank(r, q)] if rank is not None]
        found = [r for _, _, r in sorted(ranked, key=lambda item: item[:2])]
    return [{"name": r.name, "title": r.title, "bus": r.bus} for r in found]
