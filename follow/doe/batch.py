"""One experiment, many structural variants.

Plain git has no concept for this: a factorial DOE (design of experiments) split across, say,
25 wafers is still *one* experiment - one intent, one protocol, one conclusion - but its
``Structure`` holds many sibling entities (wafers, cake batches, lens blanks, barbecue grates...)
that each got a different combination of parameters. Follow already lets a ``Structure`` hold
``list[SomeSubStructure]`` (see ``examples/solar_cell.py``'s ``SolarModule.cells``); this module
adds the generic analysis that makes that list useful for a DOE specifically: given N sibling
entities, which parameters are the same across all of them (the shared baseline) and which vary
(the actual DOE factors), read off mechanically rather than tracked by hand.

This has nothing domain-specific in it - it walks dumped dicts the same way
:mod:`follow.paths.diffing` does, just N-way instead of 2-way - so it works identically whether the
entities are wafers, recipes, lens shapes, or anything else.
"""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel

from ..core.errors import BatchShapeError
from ..paths.formatting import is_quantity_leaf
from ..paths.merging import get_path, split_path


class BatchFactor(BaseModel):
    """One leaf parameter that differs across the batch's entities, with each entity's value in
    the same order the entities were given to :func:`analyze_batch`.
    """

    path: str
    values: list[Any]


class BatchVariation(BaseModel):
    """The result of :func:`analyze_batch`: every leaf parameter split into ``constant`` (the
    same value on every entity - the shared baseline) or ``varying`` (a real DOE factor).
    """

    entity_count: int
    constant: dict[str, Any] = {}
    varying: list[BatchFactor] = []

    @property
    def is_uniform(self) -> bool:
        """True if every entity is identical - there is nothing to explode."""
        return not self.varying


def _leaf_paths(value: Any, path: str, out: list[str]) -> None:
    if is_quantity_leaf(value):
        out.append(path)
        return
    if isinstance(value, dict):
        for key in value:
            out_path = f"{path}.{key}" if path else key
            _leaf_paths(value[key], out_path, out)
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _leaf_paths(item, f"{path}[{i}]", out)
        return
    out.append(path)


def analyze_batch(entities: Sequence[Any], *, ignore: Sequence[str] = ()) -> BatchVariation:
    """Compare N sibling entities (``Structure``/``BaseModel`` instances, or plain dumped
    dicts - e.g. ``repo.load_structure(exp).wafers``) leaf by leaf and split every parameter
    into ``constant`` (identical everywhere) or ``varying`` (an actual DOE factor), with each
    entity's value for the ones that vary.

    Entities are expected to share the same shape (typically: all instances of the same
    ``Structure`` subclass) - the leaf paths are read off the first entity and looked up on the
    rest, so a genuinely heterogeneous list raises a plain ``KeyError``/``IndexError`` rather
    than silently comparing the wrong things.

    Pass ``ignore`` for top-level fields that identify each entity rather than parametrize it
    (a wafer slot number, a recipe name, a serial id) - these are expected to differ on every
    entity and would otherwise never let a genuinely uniform batch (e.g. a confirmation lot run
    at a single settled combination) come back as ``is_uniform``.
    """
    dumps = [e.model_dump(mode="json") if isinstance(e, BaseModel) else e for e in entities]
    if not dumps:
        return BatchVariation(entity_count=0)

    # The union of every entity's leaf paths, in order of first appearance - not just the first
    # entity's. Reading them off dumps[0] alone was asymmetric: an extra field on entity 2..N was
    # dropped from the analysis without a word (a real DOE factor missing from the report), while
    # the mirror case - a field only entity 1 had - did raise. Heterogeneity is now reported
    # whichever entity the extra field is on.
    paths: list[str] = []
    seen: set[str] = set()
    for dump in dumps:
        entity_paths: list[str] = []
        _leaf_paths(dump, "", entity_paths)
        for path in entity_paths:
            if path not in seen:
                seen.add(path)
                paths.append(path)

    ignored = set(ignore)

    constant: dict[str, Any] = {}
    varying: list[BatchFactor] = []
    for path in paths:
        if path.split(".", 1)[0].split("[", 1)[0] in ignored:
            continue
        tokens = split_path(path)
        values = []
        for index, dump in enumerate(dumps):
            try:
                values.append(get_path(dump, tokens))
            except (KeyError, IndexError, TypeError) as exc:
                raise BatchShapeError(
                    f"entity {index} has no {path!r}, but another entity in this batch does - "
                    "analyze_batch compares entities of the same shape (typically all instances "
                    "of one Structure subclass); a genuinely optional field cannot be told apart "
                    "from a missing one here"
                ) from exc
        if all(v == values[0] for v in values):
            constant[path] = values[0]
        else:
            varying.append(BatchFactor(path=path, values=values))

    return BatchVariation(entity_count=len(dumps), constant=constant, varying=varying)
