from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from .formatting import format_value, is_quantity_leaf
from ..core.structure import Structure

_MISSING = object()


class DiffEntry(BaseModel):
    """One leaf-level difference between two structures, addressed by a dotted/indexed path."""

    path: str
    kind: Literal["added", "removed", "changed"]
    before: Any = None
    after: Any = None

    def __str__(self) -> str:
        if self.kind == "added":
            return f"+ {self.path}: {format_value(self.after)}"
        if self.kind == "removed":
            return f"- {self.path}: {format_value(self.before)}"
        return f"~ {self.path}: {format_value(self.before)} -> {format_value(self.after)}"


class StructureDiff(BaseModel):
    """The full set of leaf-level differences between two :class:`Structure` instances."""

    entries: list[DiffEntry] = []

    @property
    def changed_paths(self) -> list[str]:
        return [e.path for e in self.entries]

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)


def _walk(before: Any, after: Any, path: str, out: list[DiffEntry]) -> None:
    if before is _MISSING:
        out.append(DiffEntry(path=path, kind="added", after=after))
        return
    if after is _MISSING:
        out.append(DiffEntry(path=path, kind="removed", before=before))
        return

    both_dicts = isinstance(before, dict) and isinstance(after, dict)
    if both_dicts and not (is_quantity_leaf(before) and is_quantity_leaf(after)):
        for key in sorted(set(before) | set(after)):
            sub_path = f"{path}.{key}" if path else key
            _walk(before.get(key, _MISSING), after.get(key, _MISSING), sub_path, out)
        return

    if isinstance(before, list) and isinstance(after, list):
        for i in range(max(len(before), len(after))):
            b = before[i] if i < len(before) else _MISSING
            a = after[i] if i < len(after) else _MISSING
            _walk(b, a, f"{path}[{i}]", out)
        return

    if before != after:
        out.append(DiffEntry(path=path, kind="changed", before=before, after=after))


def diff_structures(
    before: Structure | dict | list | None, after: Structure | dict | list | None
) -> StructureDiff:
    """Recursively compare two structures leaf by leaf, regardless of their domain.

    Works on any :class:`Structure` subclass, or a plain dict/list/None straight from
    ``model_dump`` (e.g. a list of :class:`~follow.core.models.Step`), without knowing anything
    about recipes, MOSFETs or solar cells - it only walks the fields Pydantic already knows
    about. A :class:`~follow.core.quantity.Quantity` (a dict with a ``value`` key) is treated as a
    single leaf so e.g. a value/unit pair changes together rather than as two unrelated diffs.
    """
    before_dump = before.model_dump(mode="json") if isinstance(before, BaseModel) else ({} if before is None else before)
    after_dump = after.model_dump(mode="json") if isinstance(after, BaseModel) else ({} if after is None else after)
    entries: list[DiffEntry] = []
    _walk(before_dump, after_dump, "", entries)
    return StructureDiff(entries=entries)
