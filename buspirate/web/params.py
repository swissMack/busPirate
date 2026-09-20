"""Turning whatever the browser sent into the types handlers expect.

The dashboard's forms are generated from the parameter schema, so this is the
one place that has to be forgiving: an address may arrive as ``0x50``, ``50``
or ``80``, and a byte string as ``de ad be ef``, ``DEADBEEF`` or
``0xDE, 0xAD``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .registry import Param


class ParamError(ValueError):
    """The value the browser sent cannot be used. The message is user-facing."""


def coerce_all(params: List[Param], raw: Dict[str, Any]) -> Dict[str, Any]:
    values = {}
    for param in params:
        given = raw.get(param.name, param.default)
        values[param.name] = coerce(param, given)
    return values


def coerce(param: Param, value: Any) -> Any:
    handler = _HANDLERS[param.type]
    try:
        return handler(param, value)
    except ParamError:
        raise
    except (TypeError, ValueError) as exc:
        raise ParamError(f"{param.label}: {exc}") from exc


def _as_int(param: Param, value: Any, base: int = 10) -> int:
    if isinstance(value, bool):
        raise ParamError(f"{param.label}: expected a number")
    if isinstance(value, int):
        number = value
    else:
        text = str(value).strip().replace("_", "")
        if not text:
            raise ParamError(f"{param.label}: needs a value")
        if text.lower().startswith("0x"):
            number = int(text, 16)
        elif base == 16 and not text.isdigit():
            number = int(text, 16)
        else:
            number = int(text, base)
    if param.minimum is not None and number < param.minimum:
        raise ParamError(f"{param.label}: must be at least {param.minimum}")
    if param.maximum is not None and number > param.maximum:
        raise ParamError(f"{param.label}: must be at most {param.maximum}")
    return number


def _int(param: Param, value: Any) -> int:
    return _as_int(param, value)


def _hex(param: Param, value: Any) -> int:
    """Hex by default, so a bare ``50`` in an address box means 0x50."""
    if isinstance(value, int):
        return _as_int(param, value)
    return _as_int(param, value, base=16)


def _bool(param: Param, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _enum(param: Param, value: Any) -> Any:
    allowed = [choice["value"] for choice in param.choices or []]
    if value in allowed:
        return value
    # Browsers hand back strings even for numeric options.
    for candidate in allowed:
        if str(candidate) == str(value):
            return candidate
    labels = ", ".join(str(a) for a in allowed)
    raise ParamError(f"{param.label}: choose one of {labels}")


def _bytes(param: Param, value: Any) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, list):
        return bytes(int(v) & 0xFF for v in value)
    text = str(value).strip()
    if not text:
        return b""
    cleaned = re.sub(r"(?i)0x|[,\s:_-]", "", text)
    if not re.fullmatch(r"[0-9a-fA-F]*", cleaned):
        raise ParamError(
            f"{param.label}: expected hex bytes, for example 'de ad be ef'"
        )
    if len(cleaned) % 2:
        raise ParamError(
            f"{param.label}: hex needs an even number of digits "
            f"(got {len(cleaned)})"
        )
    return bytes.fromhex(cleaned)


def _text(param: Param, value: Any) -> str:
    return "" if value is None else str(value)


def _filename(param: Param, value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise ParamError(f"{param.label}: needs a file name")
    if "/" in name or "\\" in name or name.startswith("."):
        raise ParamError(
            f"{param.label}: use a plain file name — files are written to captures/"
        )
    return name


_HANDLERS = {
    "int": _int,
    "hex": _hex,
    "bool": _bool,
    "enum": _enum,
    "bytes": _bytes,
    "text": _text,
    "filename": _filename,
}
