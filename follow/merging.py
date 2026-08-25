from __future__ import annotations

import copy
import re
from typing import Any, Iterable

from .errors import MalformedPathError, PathNotFoundError

_TOKEN = re.compile(r"\.?([^.\[\]]+)|\[(\d+)\]")


def split_path(path: str) -> list[str | int]:
    """Parse a dotted/indexed path (the format :class:`~follow.diffing.DiffEntry` uses, e.g.
    ``"ingredients.flour"`` or ``"steps[2].parameters.temperature"``) into the sequence of
    dict-key/list-index tokens needed to walk a dumped structure.

    Dict keys containing a literal ``.``, ``[`` or ``]`` cannot round-trip through this format
    (they would be misread as extra path segments) - avoid such keys in ``Structure`` fields
    that hold a ``dict`` (e.g. ``ingredients: dict[str, Quantity]``) if you plan to merge on them.

    Raises :class:`ValueError` on a malformed path (e.g. a non-numeric index like
    ``"steps[abc]"``) rather than silently misreading it as something else - a wrong path here
    would otherwise merge or diff the wrong value with no indication anything went wrong.
    """
    tokens: list[str | int] = []
    pos = 0
    while pos < len(path):
        match = _TOKEN.match(path, pos)
        if match is None:
            raise MalformedPathError(f"malformed path {path!r}: unexpected {path[pos:pos + 20]!r} at position {pos}")
        name, index = match.groups()
        tokens.append(int(index) if index is not None else name)
        pos = match.end()
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
    only ``theirs`` has, but a whole new branch of the tree cannot be conjured up) - a path that
    doesn't exist on either side raises with the full path in the message, not just the segment
    that failed.
    """
    merged = copy.deepcopy(ours)
    for path in take_from_theirs:
        tokens = split_path(path)
        if not tokens:
            raise MalformedPathError(
                f"cannot take the whole root object via an empty path ({path!r}); "
                "pass explicit sub-paths (e.g. from repo.diff(...)) instead"
            )
        try:
            value = get_path(theirs, tokens)
        except (KeyError, IndexError, TypeError) as exc:
            raise PathNotFoundError(f"path {path!r} not found on the side being taken from: {exc}") from exc
        try:
            _set(merged, tokens, copy.deepcopy(value))
        except (KeyError, IndexError, TypeError) as exc:
            raise PathNotFoundError(f"path {path!r} not found on the side being kept: {exc}") from exc
    return merged
