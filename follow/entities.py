"""Track one physical thing (a mold, a wafer, a sample - anything you gave a name to) across
several *separate* experiments, without hand-maintained references.

This is a different axis from :mod:`follow.batch`: a batch is N variants inside *one*
experiment; this is *one* physical entity that shows up across *several* experiments over time
(a batch experiment creates 25 wafers, then wafer #13 specifically gets its own follow-up
experiment weeks later - two commits, related by which physical thing they're both about, not
by git parentage).

Give any ``Structure`` (or a nested sub-structure, e.g. one entry in a batch's list field) an
``entity_id`` field - any string you pick, like ``"moule-vert"`` or ``"wafer-A3"``. Nothing else
is required: no reference to set, no id to look up and copy. :func:`find_entity_mentions` (and
:meth:`Repository.find_entity <follow.repository.Repository.find_entity>`, built on it) find
every experiment that used the same name by walking each experiment's already-stored structure
dump - the same shape-based walk :mod:`follow.diffing`/:mod:`follow.batch` already do, here
searching for one specific leaf instead of comparing several. Two experiments that never
reference each other, on unrelated branches, still turn up in the same entity's timeline as long
as they agree on the name.
"""

from __future__ import annotations

from typing import Any


def find_entity_mentions(structure: Any, entity_id: str) -> list[str]:
    """Every path within a dumped ``Structure`` (a plain dict, e.g. ``Experiment.structure``)
    whose ``entity_id`` field equals ``entity_id``. Empty list if the entity isn't mentioned at
    all, or if ``entity_id`` itself is falsy (``None``/``""`` never matches - most structures
    have plenty of fields that are simply *absent* rather than set, and treating "absent" as a
    match for "no name given" would flag nearly everything). ``[""]`` if the structure's own
    top-level ``entity_id`` matches (the whole experiment *is* that entity, not just one item
    inside it).
    """
    if not entity_id:
        return []
    paths: list[str] = []
    _walk(structure, "", entity_id, paths)
    return paths


def _walk(value: Any, path: str, entity_id: str, out: list[str]) -> None:
    if isinstance(value, dict):
        if value.get("entity_id") == entity_id:
            out.append(path)
        for key, child in value.items():
            _walk(child, f"{path}.{key}" if path else key, entity_id, out)
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _walk(item, f"{path}[{i}]", entity_id, out)


def list_entity_ids(structure: Any) -> list[str]:
    """Every distinct, non-empty ``entity_id`` value present anywhere in a dumped ``Structure``,
    sorted. The mirror of :func:`find_entity_mentions`: that one answers "where does *this*
    entity show up", this one answers "which entities does this structure name at all" - what a
    GUI needs to surface an experiment's physical entities prominently (with a link to trace
    each one) instead of leaving them buried in a nested JSON blob.
    """
    found: set[str] = set()
    _collect(structure, found)
    return sorted(found)


def _collect(value: Any, out: set[str]) -> None:
    if isinstance(value, dict):
        entity_id = value.get("entity_id")
        if entity_id:
            out.add(entity_id)
        for child in value.values():
            _collect(child, out)
        return
    if isinstance(value, list):
        for item in value:
            _collect(item, out)
