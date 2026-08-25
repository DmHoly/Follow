"""Where a repository's experiments and refs are kept - and how to keep them somewhere else.

:class:`~follow.storage.repository.Repository` used to be its own storage backend: ``if self.path is not
None`` guarded every write, the JSON layout was inlined in its methods, and the in-memory case
was that same code path with the guards falsy. Two things followed. Changing the backend (SQLite,
an object store, a remote) meant editing the class that also holds the commit rules; and testing
those rules against a persisted repository meant writing real files.

So persistence is a collaborator now. :class:`ObjectStore` is the contract, and there are two
implementations: :class:`MemoryStore` (keeps nothing, for notebooks and tests) and
:class:`JsonFileStore` (one file per experiment plus a refs file - the layout Follow already
used, unchanged on disk). ``Repository`` keeps holding its objects and refs in memory; what it no
longer does is decide how they reach a disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .commit_form import CommitForm
    from ..core.models import Experiment


def write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so a reader only ever sees the old file or the new one.

    A plain ``write_text`` truncates the file and then fills it: interrupt it - Ctrl-C, a full
    disk, a crash - and what is left on disk is a *half* file. For ``refs.json`` that is not an
    inconvenience but a repository whose branches no longer name real objects, i.e. exactly the
    state :class:`~follow.core.errors.DanglingRefError` reports. Writing to a temporary file in the
    same directory and then ``os.replace``-ing it over the target makes the swap atomic on POSIX
    and on Windows, so the old file stands until the new one is complete.

    Note what this does *not* solve: two processes committing to the same repository at once
    still overwrite each other's refs, because each holds a whole in-memory view read before the
    other's write. Atomicity keeps every individual file readable; it is not a lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())  # the bytes must be on disk before the name points at them
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)  # never leave a stray .tmp behind, not even on Ctrl-C
        raise


class ObjectStore:
    """Where a repository's experiments and refs live between processes.

    The default implementation is :class:`MemoryStore`'s: remember nothing. A backend overrides
    the three operations a repository actually performs - read everything at open, append one
    experiment, replace the refs - plus :meth:`default_commit_form` for backends that can carry a
    form template alongside the data.
    """

    def load(self) -> tuple[dict[str, "Experiment"], dict[str, str], dict[str, str]]:
        """Everything already stored: ``(experiments_by_id, branches, tags)``."""
        return {}, {}, {}

    def add_experiment(self, experiment: "Experiment") -> None:
        """Persist one newly committed, immutable experiment."""

    def write_refs(self, branches: dict[str, str], tags: dict[str, str]) -> None:
        """Persist the branch and tag tables, replacing what was there."""

    def default_commit_form(self) -> "CommitForm | None":
        """A commit form the store itself carries, used when the caller passed none."""
        return None


class MemoryStore(ObjectStore):
    """Keeps nothing: the repository lives and dies with the process.

    This is not a stub standing in for the real thing - it is the backend an in-memory
    ``Repository()`` genuinely uses, which is why it inherits the base class's do-nothing
    operations rather than reimplementing them.
    """


class JsonFileStore(ObjectStore):
    """Plain JSON on disk: ``objects/<id>.json`` per experiment, plus ``refs.json``.

    Human-readable and diffable on purpose - a Follow repository can itself be tracked in git.
    Writes go through :func:`write_atomic`, so an interrupted commit cannot leave a torn file.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> tuple[dict[str, "Experiment"], dict[str, str], dict[str, str]]:
        from ..core.models import Experiment

        experiments: dict[str, Experiment] = {}
        branches: dict[str, str] = {}
        tags: dict[str, str] = {}
        if not self.path.exists():
            return experiments, branches, tags

        objects_dir = self.path / "objects"
        if objects_dir.exists():
            for file in objects_dir.glob("*.json"):
                experiment = Experiment.model_validate_json(file.read_text(encoding="utf-8"))
                experiments[experiment.id] = experiment

        refs_file = self.path / "refs.json"
        if refs_file.exists():
            refs = json.loads(refs_file.read_text(encoding="utf-8"))
            branches = dict(refs.get("branches", {}))
            tags = dict(refs.get("tags", {}))
        return experiments, branches, tags

    def add_experiment(self, experiment: "Experiment") -> None:
        write_atomic(self.path / "objects" / f"{experiment.id}.json", experiment.model_dump_json(indent=2))

    def write_refs(self, branches: dict[str, str], tags: dict[str, str]) -> None:
        write_atomic(
            self.path / "refs.json",
            json.dumps({"branches": branches, "tags": tags}, indent=2, sort_keys=True),
        )

    def default_commit_form(self) -> "CommitForm | None":
        """``<path>/commit_form.yml`` if it is there - dropping one into an existing repository's
        directory is enough to start requiring it from then on.
        """
        from .commit_form import load_commit_form

        candidate = self.path / "commit_form.yml"
        return load_commit_form(candidate) if candidate.exists() else None
