from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict

from ..paths.formatting import format_value

ScalarValue = Union[float, int, str, bool]


class Quantity(BaseModel):
    """A measured or specified value, with the unit/uncertainty needed to compare it across
    experiments. Leave ``unit`` unset (``None``) for a dimensionless value - an empty string is
    treated the same as unset by :func:`~follow.paths.formatting.format_value` (both are falsy), so
    don't rely on ``unit=""`` to mean something different from no unit at all.
    """

    model_config = ConfigDict(frozen=True)

    value: ScalarValue
    unit: str | None = None
    uncertainty: float | None = None
    note: str | None = None

    def __str__(self) -> str:
        """The same rendering :func:`~follow.paths.formatting.format_value` gives the dumped form.

        These were two separate implementations that had already drifted: this one dropped
        ``note`` entirely, so a fiche showed the note on values reached through the structure
        (formatted from the dump) and silently lost it on step parameters and evidence metrics
        (formatted through ``str``). One renderer, one output.
        """
        return format_value(
            {"value": self.value, "unit": self.unit, "uncertainty": self.uncertainty, "note": self.note}
        )
