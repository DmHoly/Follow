from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict

ScalarValue = Union[float, int, str, bool]


class Quantity(BaseModel):
    """A measured or specified value, with the unit/uncertainty needed to compare it across experiments."""

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
