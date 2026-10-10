"""Defensive coercion of Wingman custom-property values (shared by all layers)."""

from __future__ import annotations


def coerce_int(value: object, default: int, minimum: int) -> int:
    """Coerce a config value to an int, clamped to a sane minimum.

    Falls back to ``default`` when the value is missing or non-numeric, so a
    manually-edited or stringified config cannot crash the skill.
    """
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(minimum, result)


def coerce_bool(value: object, default: bool) -> bool:
    """Coerce a config value to a bool, parsing strings explicitly.

    Guards against ``bool("false") is True`` when the UI yields a string.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "on"):
            return True
        if text in ("false", "0", "no", "off", ""):
            return False
    return default
