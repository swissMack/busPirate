"""Single-use confirmation tokens for plan/apply tools."""

from __future__ import annotations

import secrets
import time
from typing import Any, Callable, Dict, Tuple


class ConfirmError(ValueError):
    """The token is unknown, expired, already used, or for another action."""


class ConfirmStore:
    def __init__(self, ttl: float = 300.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._items = {}  # type: Dict[str, Tuple[str, Any, float]]

    def issue(self, action: str, payload: Any) -> str:
        token = secrets.token_hex(8)
        self._items[token] = (action, payload, self._clock() + self._ttl)
        return token

    def redeem(self, token: str, action: str) -> Any:
        item = self._items.pop(token, None)  # consumed even if it fails below
        if item is None:
            raise ConfirmError("unknown or already-used confirmation token; "
                               "plan again to get a new one")
        stored_action, payload, expires = item
        if self._clock() > expires:
            raise ConfirmError("confirmation token expired; plan again")
        if stored_action != action:
            raise ConfirmError("token was issued for %r, not %r; plan again"
                               % (stored_action, action))
        return payload
