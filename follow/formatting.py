from __future__ import annotations

from typing import Any

_QUANTITY_KEYS = {"value", "unit", "uncertainty", "note"}


def is_quantity_leaf(value: Any) -> bool:
    """True for a dumped Quantity (a dict with a ``value`` key and no other unknown keys)."""
    return isinstance(value, dict) and "value" in value and set(value).issubset(_QUANTITY_KEYS)


def format_value(value: Any) -> str:
    """Render a dumped structure leaf - a Quantity dict or a plain scalar - for humans."""
    if not is_quantity_leaf(value):
        return str(value)
    parts = [str(value["value"])]
    if value.get("unit"):
        parts.append(value["unit"])
    if value.get("uncertainty") is not None:
        parts.append(f"± {value['uncertainty']}")
    text = " ".join(parts)
    if value.get("note"):
        text += f" ({value['note']})"
    return text
