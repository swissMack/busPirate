"""The one open board: opened on request, serialised, dropped when unplugged."""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, FrozenSet, List, Optional, TypeVar

from .. import ports
from ..connect import open_device, open_simulated
from ..exceptions import PortGoneError
from .power import PowerPlan

T = TypeVar("T")


class NotConnected(RuntimeError):
    """No board is open, or none could be opened."""


class BoardGone(RuntimeError):
    """The board was unplugged mid-use; the session has dropped it."""


class BoardSession:
    def __init__(
        self,
        opener: Optional[Callable[[str], Any]] = None,
        discover=ports.discover,
        simulated: Optional[str] = None,
    ) -> None:
        self._opener = opener
        self._discover = discover
        self._simulated = simulated
        self._lock = threading.Lock()
        self.board: Any = None
        self.port: Optional[str] = None
        self.power: Optional[PowerPlan] = None

    # -- discovery / connection ---------------------------------------------

    def candidates(self) -> List[str]:
        if self._simulated:
            return ["simulated-" + self._simulated]
        found = []
        for c in self._discover(include_unlikely=False):
            likely = c.likely_bus_pirate
            if callable(likely):  # a method on test stubs, a property on PortCandidate
                likely = likely()
            if likely:
                found.append(c.device)
        return found

    def _open(self, port: str) -> Any:
        if self._simulated:
            return open_simulated(self._simulated)
        if self._opener is not None:
            return self._opener(port)
        return open_device(ports.resolve(port), usb_id=ports.usb_id_for(port))

    def connect(self, port: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if self.board is not None:
                self._drop()
            if port is None:
                found = self.candidates()
                if not found:
                    raise NotConnected(
                        "no board found — plug in the Bus Pirate or Bit Pirate and try again"
                    )
                if len(found) > 1:
                    return {"connected": False, "choose_from": found}
                port = found[0]
            try:
                board = self._open(port)
            except OSError as exc:
                if "busy" in str(exc).lower():
                    raise NotConnected(
                        "%s is held by another program — close the dashboard or "
                        "terminal using it" % port
                    ) from exc
                raise
            self.board, self.port = board, port
            try:
                profile = board.profile
                return {
                    "connected": True,
                    "port": port,
                    "board": profile.describe(),
                    "variant": profile.variant,
                    "capabilities": sorted(profile.capabilities),
                }
            except Exception:
                self._drop()
                raise

    def _drop(self) -> None:
        board, self.board, self.port, self.power = self.board, None, None, None
        if board is not None:
            try:
                board.close()
            except Exception:
                pass

    def disconnect(self) -> None:
        with self._lock:
            self._drop()

    # -- state ---------------------------------------------------------------

    # Each reads the attribute once: a bus tool's worker thread may drop the
    # board (and its power) between two reads.

    @property
    def variant(self) -> Optional[str]:
        board = self.board
        return board.profile.variant if board is not None else None

    @property
    def capabilities(self) -> FrozenSet[str]:
        board = self.board
        if board is None:
            return frozenset()
        return frozenset(board.profile.capabilities)

    def peripherals(self) -> Dict[str, bool]:
        power = self.power
        return {"power": power is not None, "pullups": bool(power and power.pullups)}

    # -- use -------------------------------------------------------------------

    def run(self, fn: Callable[[Any], T]) -> T:
        with self._lock:
            if self.board is None:
                raise NotConnected("no board is connected — call connect first")
            try:
                return fn(self.board)
            except (PortGoneError, OSError) as exc:
                self._drop()
                raise BoardGone("board disconnected") from exc
