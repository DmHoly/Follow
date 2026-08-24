from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict

ScalarValue = Union[float, int, str, bool]


class Quantity(BaseModel):
    """A measured or specified value, with the unit/uncertainty needed to compare it across
    experiments. Leave ``unit`` unset (``None``) for a dimensionless value - an empty string is
    treated the same as unset by :func:`~follow.formatting.format_value` (both are falsy), so
    don't rely on ``unit=""`` to mean something different from no unit at all.
    """

    model_config = ConfigDict(frozen=True)

    value: ScalarValue
    unit: str | None = None
    uncertainty: float | None = None
    note: str | None = None

    def __str__(self) -> str:
        parts = [str(self.value)]
        if self.unit:
            parts.append(self.unit)
        if self.uncertainty is not None:
            parts.append(f"± {self.uncertainty}")
        return " ".join(parts)
