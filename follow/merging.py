from __future__ import annotations

import copy
import re
from typing import Any, Iterable

_PATH_SEGMENT = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def split_path(path: str) -> list[str | int]:
    """Parse a dotted/indexed path (the format :class:`~follow.diffing.DiffEntry` uses, e.g.
    ``"ingredients.flour"`` or ``"steps[2].parameters.temperature"``) into the sequence of
    dict-key/list-index tokens needed to walk a dumped structure.
    """
    tokens: list[str | int] = []
    for name, index in _PATH_SEGMENT.findall(path):
        tokens.append(int(index) if index else name)
    return tokens


def get_path(obj: Any, tokens: list[str | int]) -> Any:
    """Walk ``tokens`` (from :func:`split_path`) into a dumped dict/list and return the value."""
    for token in tokens:
        obj = obj[token]
    return obj


def _set(obj: Any, tokens: list[str | int], value: Any) -> None:
    for token in tokens[:-1]:
        obj = obj[token]
    obj[tokens[-1]] = value


def resolve_merge_paths(ours: Any, theirs: Any, take_from_theirs: Iterable[str]) -> Any:
    """Merge two dumped structures (dict/list, straight from ``model_dump``) by starting from
    ``ours`` and overwriting the given paths - in the same dotted/indexed format
    :class:`~follow.diffing.DiffEntry` uses, so you can copy them straight out of a
    ``repo.diff(...)`` listing - with the value at that path in ``theirs``.

    This is Follow's conflict-resolution primitive: nothing is guessed automatically, every
    path you don't list keeps the ``ours`` value, exactly like an untouched hunk in a git merge.
    A path's parent container must already exist in both sides (a leaf can be new, e.g. a key
    only ``theirs`` has, but a whole new branch of the tree cannot be conjured up).
    """
    merged = copy.deepcopy(ours)
    for path in take_from_theirs:
        tokens = split_path(path)
        _set(merged, tokens, copy.deepcopy(get_path(theirs, tokens)))
    return merged
