from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .diffing import StructureDiff, diff_structures
from .ids import content_id
from .models import Conclusion, Evidence, Experiment, Objective, ReferenceLink, Step
from .structure import Structure


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FollowError(Exception):
    """Base class for Follow errors."""


class ExperimentNotFoundError(FollowError, KeyError):
    def __init__(self, ref: str):
        super().__init__(f"No experiment, branch or tag matches {ref!r}")
        self.ref = ref


class ExperimentBuilder:
    """A mutable, in-progress experiment - the equivalent of git's working tree + index.

    Created via :meth:`Repository.new` or :meth:`Repository.derive`, freely edited while the
    experiment is being planned and run, then frozen into an immutable :class:`Experiment`
    with :meth:`commit`.
    """

    def __init__(
        self,
        repo: "Repository",
        *,
        branch: str,
        parents: list[str],
        structure: Structure,
        title: str,
        intent: str,
        author: str | None = None,
        hypothesis: str | None = None,
        references: Iterable[ReferenceLink] = (),
        objectives: Iterable[Objective] = (),
        steps: Iterable[Step] = (),
        tags: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.repo = repo
        self.branch = branch
        self.parents = list(parents)
        self.structure = structure
        self.title = title
        self.intent = intent
        self.author = author
        self.hypothesis = hypothesis
        self.references: list[ReferenceLink] = list(references)
        self.objectives: list[Objective] = list(objectives)
        self.steps: list[Step] = list(steps)
        self.evidence: list[Evidence] = []
        self.conclusion = Conclusion()
        self.tags: list[str] = list(tags)
        self.metadata: dict[str, Any] = dict(metadata or {})

    def add_objective(self, **kwargs: Any) -> "ExperimentBuilder":
        self.objectives.append(Objective(**kwargs))
        return self

    def add_reference(self, **kwargs: Any) -> "ExperimentBuilder":
        self.references.append(ReferenceLink(**kwargs))
        return self

    def add_step(self, **kwargs: Any) -> "ExperimentBuilder":
        kwargs.setdefault("order", len(self.steps) + 1)
        self.steps.append(Step(**kwargs))
        return self

    def add_evidence(self, **kwargs: Any) -> "ExperimentBuilder":
        self.evidence.append(Evidence(**kwargs))
        return self

    def conclude(self, **kwargs: Any) -> "ExperimentBuilder":
        kwargs.setdefault("status", "concluded")
        kwargs.setdefault("decided_at", _utcnow())
        self.conclusion = Conclusion(**kwargs)
        return self

    def diff_from_baseline(self) -> StructureDiff | None:
        """The structural diff against this experiment's baseline reference, if it has one.

        This is how "which parameters actually varied" gets answered without either side
        having to track it by hand - it falls out of comparing two Structure instances.
        """
        baseline = next((r for r in self.references if r.role == "baseline" and r.experiment_id), None)
        if baseline is None:
            return None
        parent_structure = self.repo.load_structure(self.repo.get(baseline.experiment_id))
        return diff_structures(parent_structure, self.structure)

    def commit(self) -> Experiment:
        return self.repo._commit(self)


class Repository:
    """A store of experiments and the branches/tags pointing into their lineage - Follow's
    equivalent of a git repository. Experiments are content-addressed and immutable once
    committed; branches are mutable pointers to the latest experiment on a line of work.

    Pass ``path`` to persist to plain JSON files (one per experiment, plus a refs file), or
    leave it out for an in-memory repository (handy for tests and notebooks).
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else None
        self._objects: dict[str, Experiment] = {}
        self._branches: dict[str, str] = {}
        self._tags: dict[str, str] = {}
        if self.path is not None and self.path.exists():
            self._load()

    # -- reading -----------------------------------------------------------------

    @property
    def branches(self) -> dict[str, str]:
        return dict(self._branches)

    @property
    def tags(self) -> dict[str, str]:
        return dict(self._tags)

    def __len__(self) -> int:
        return len(self._objects)

    def __iter__(self) -> Iterator[Experiment]:
        return iter(self._objects.values())

    def __contains__(self, ref: str) -> bool:
        try:
            self._resolve_ref(ref)
        except ExperimentNotFoundError:
            return False
        return True

    def _resolve_ref(self, ref: str) -> str:
        if ref in self._branches:
            return self._branches[ref]
        if ref in self._tags:
            return self._tags[ref]
        if ref in self._objects:
            return ref
        raise ExperimentNotFoundError(ref)

    def get(self, ref: str) -> Experiment:
        """Resolve a branch name, tag name, or experiment id to its Experiment."""
        return self._objects[self._resolve_ref(ref)]

    def load_structure(self, experiment: Experiment) -> Structure:
        cls = Structure.resolve(experiment.structure_type)
        return cls.model_validate(experiment.structure)

    def log(self, ref: str) -> list[Experiment]:
        """First-parent history from ``ref`` back to the root, newest first - like `git log`."""
        history: list[Experiment] = []
        current: str | None = self._resolve_ref(ref)
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            exp = self._objects[current]
            history.append(exp)
            current = exp.parents[0] if exp.parents else None
        return history

    def graph(self) -> dict[str, list[str]]:
        """The full lineage DAG as ``{experiment_id: [parent_ids]}``, for external visualization."""
        return {exp.id: list(exp.parents) for exp in self._objects.values()}

    def diff(self, ref_a: str, ref_b: str) -> StructureDiff:
        a, b = self.get(ref_a), self.get(ref_b)
        return diff_structures(self.load_structure(a), self.load_structure(b))

    # -- writing -------------------------------------------------------------------

    def new(
        self,
        *,
        branch: str,
        structure: Structure,
        title: str,
        intent: str,
        author: str | None = None,
        hypothesis: str | None = None,
        parents: list[str] | None = None,
        references: Iterable[ReferenceLink] = (),
        objectives: Iterable[Objective] = (),
        steps: Iterable[Step] = (),
        tags: Iterable[str] = (),
    ) -> ExperimentBuilder:
        """Start an experiment on ``branch``. If the branch already has a tip, it becomes the
        parent automatically (continuing that line of work), unless ``parents`` is given.
        """
        parent_ids = parents if parents is not None else ([self._branches[branch]] if branch in self._branches else [])
        return ExperimentBuilder(
            self,
            branch=branch,
            parents=parent_ids,
            structure=structure,
            title=title,
            intent=intent,
            author=author,
            hypothesis=hypothesis,
            references=references,
            objectives=objectives,
            steps=steps,
            tags=tags,
        )

    def derive(
        self,
        ref: str,
        *,
        title: str,
        intent: str,
        new_branch: str | None = None,
        structure: Structure | None = None,
        author: str | None = None,
        hypothesis: str | None = None,
        carry_objectives: bool = True,
        carry_references: bool = True,
    ) -> ExperimentBuilder:
        """Branch off an existing experiment: the equivalent of `git checkout -b <new_branch> <ref>`.

        The parent's structure, objectives and references are carried over as a starting point
        (override any of them before committing), and a "baseline" reference back to the parent
        is added automatically unless one is already present - that's what makes every derived
        experiment comparable to what it came from without extra bookkeeping.
        """
        parent = self.get(ref)
        builder = ExperimentBuilder(
            self,
            branch=new_branch or parent.branch,
            parents=[parent.id],
            structure=structure if structure is not None else self.load_structure(parent),
            title=title,
            intent=intent,
            author=author,
            hypothesis=hypothesis,
            objectives=parent.objectives if carry_objectives else (),
            references=parent.references if carry_references else (),
        )
        if not any(r.role == "baseline" for r in builder.references):
            builder.add_reference(role="baseline", experiment_id=parent.id, label=f"parent: {parent.title}")
        return builder

    def branch(self, name: str, at: str) -> None:
        """Point branch ``name`` at the experiment resolved by ``at`` (id, branch, or tag)."""
        self._branches[name] = self._resolve_ref(at)
        if self.path is not None:
            self._persist_refs()

    def tag(self, name: str, at: str) -> None:
        """Point tag ``name`` (an immutable label) at the experiment resolved by ``at``."""
        self._tags[name] = self._resolve_ref(at)
        if self.path is not None:
            self._persist_refs()

    def _commit(self, builder: ExperimentBuilder) -> Experiment:
        structure_type = type(builder.structure).registry_key()
        provisional = Experiment(
            id="pending",
            parents=builder.parents,
            branch=builder.branch,
            author=builder.author,
            title=builder.title,
            intent=builder.intent,
            hypothesis=builder.hypothesis,
            structure_type=structure_type,
            structure=builder.structure.model_dump(mode="json"),
            references=builder.references,
            objectives=builder.objectives,
            steps=builder.steps,
            evidence=builder.evidence,
            conclusion=builder.conclusion,
            tags=builder.tags,
            metadata=builder.metadata,
        )
        payload = provisional.model_dump(mode="json", exclude={"id"})
        experiment = provisional.model_copy(update={"id": content_id("experiment", payload)})

        self._objects[experiment.id] = experiment
        self._branches[experiment.branch] = experiment.id
        for tag in experiment.tags:
            self._tags[tag] = experiment.id

        if self.path is not None:
            self._persist_experiment(experiment)
            self._persist_refs()
        return experiment

    # -- persistence -----------------------------------------------------------------

    def _persist_experiment(self, experiment: Experiment) -> None:
        objects_dir = self.path / "objects"
        objects_dir.mkdir(parents=True, exist_ok=True)
        (objects_dir / f"{experiment.id}.json").write_text(experiment.model_dump_json(indent=2))

    def _persist_refs(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        refs = {"branches": self._branches, "tags": self._tags}
        (self.path / "refs.json").write_text(json.dumps(refs, indent=2, sort_keys=True))

    def _load(self) -> None:
        objects_dir = self.path / "objects"
        if objects_dir.exists():
            for file in objects_dir.glob("*.json"):
                exp = Experiment.model_validate_json(file.read_text())
                self._objects[exp.id] = exp
        refs_file = self.path / "refs.json"
        if refs_file.exists():
            refs = json.loads(refs_file.read_text())
            self._branches = dict(refs.get("branches", {}))
            self._tags = dict(refs.get("tags", {}))
