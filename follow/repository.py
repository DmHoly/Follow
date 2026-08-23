from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .diffing import StructureDiff, diff_structures
from .ids import content_id
from .merging import resolve_merge_paths
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


class NothingToCommitError(FollowError):
    """Raised when a commit's content is identical to its target branch's current tip - the
    same rule as `git commit` refusing with "nothing to commit, working tree clean": Follow
    never creates a new commit that says nothing a prior one didn't already say.
    """

    def __init__(self, branch: str, tip_id: str):
        super().__init__(f"nothing to commit: {branch!r} already points at {tip_id}, and this commit's content is identical")
        self.branch = branch
        self.tip_id = tip_id


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
        self._committed = False

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
        """Freeze this builder into an immutable :class:`Experiment`.

        A builder can only be committed once: committing, then continuing to edit the same
        builder and committing again does *not* amend the first commit (Follow has no amend -
        commits are immutable) - it would otherwise silently produce a sibling with the same
        parent, leaving the first commit orphaned (still in the repository, but unreachable from
        the branch tip via :meth:`Repository.log`). To avoid that footgun, a second call on the
        same builder raises; derive a new builder from the result instead.

        Committing a *different* builder (e.g. loaded fresh from an unmodified draft file - a
        CLI command or script re-run by mistake) whose content is otherwise identical to its
        branch's current tip raises :class:`NothingToCommitError` - the same rule as `git
        commit` refusing an empty diff - rather than silently duplicating that tip or silently
        doing nothing; :meth:`Repository._commit` checks content, not object identity.
        """
        if self._committed:
            raise FollowError(
                "this ExperimentBuilder was already committed - editing and recommitting it does "
                "not amend the previous commit, it creates an orphaned sibling; call "
                "repo.derive(<the id you got back>, ...) to continue instead"
            )
        experiment = self.repo._commit(self)
        self._committed = True
        return experiment

    def to_draft(self) -> dict[str, Any]:
        """Dump this builder to a plain JSON-able dict: the "working tree" file a CLI user
        edits by hand (adding steps, evidence, a conclusion...) before ``follow commit``.
        See :meth:`Repository.load_draft` for the reverse operation.
        """
        return {
            "branch": self.branch,
            "parents": self.parents,
            "structure_type": type(self.structure).registry_key(),
            "structure": self.structure.model_dump(mode="json"),
            "title": self.title,
            "intent": self.intent,
            "author": self.author,
            "hypothesis": self.hypothesis,
            "references": [r.model_dump(mode="json") for r in self.references],
            "objectives": [o.model_dump(mode="json") for o in self.objectives],
            "steps": [s.model_dump(mode="json") for s in self.steps],
            "evidence": [e.model_dump(mode="json") for e in self.evidence],
            "conclusion": self.conclusion.model_dump(mode="json"),
            "tags": self.tags,
            "metadata": self.metadata,
        }


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

    def _ensure_branch_name_available(self, name: str) -> None:
        """Branches and tags share one namespace: resolving a ref checks branches first, so a
        branch silently shadowing a same-named tag would make that tag unreachable by name with
        no warning. Only a genuinely new branch name is checked - continuing an existing branch
        is always fine.
        """
        if name not in self._branches and name in self._tags:
            raise FollowError(f"{name!r} is already a tag; branch and tag names share one namespace and must not collide")

    def _ensure_tag_assignment(self, name: str, target_id: str, *, force: bool) -> None:
        if name not in self._tags and name in self._branches:
            raise FollowError(f"{name!r} is already a branch; branch and tag names share one namespace and must not collide")
        existing = self._tags.get(name)
        if existing is not None and existing != target_id and not force:
            raise FollowError(
                f"tag {name!r} already points at {existing} - tags are immutable; "
                "pass force=True to repo.tag(...) to repoint it deliberately"
            )

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
        """Structural diff between two experiments' ``Structure`` - the config being studied."""
        a, b = self.get(ref_a), self.get(ref_b)
        return diff_structures(self.load_structure(a), self.load_structure(b))

    def diff_steps(self, ref_a: str, ref_b: str) -> StructureDiff:
        """Diff between two experiments' protocol (``steps``), the same way :meth:`diff`
        compares their structure - use it to find the ``[i]``/``[i].field`` paths to pass to
        :meth:`merge`'s ``take_steps``.
        """
        a, b = self.get(ref_a), self.get(ref_b)
        return diff_structures(
            [s.model_dump(mode="json") for s in a.steps],
            [s.model_dump(mode="json") for s in b.steps],
        )

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
        carry_steps: bool = True,
    ) -> ExperimentBuilder:
        """Branch off an existing experiment: the equivalent of `git checkout -b <new_branch> <ref>`.

        The parent's structure, objectives, protocol steps and references are carried over as a
        starting point (override any of them before committing), and a "baseline" reference back
        to the parent is added automatically unless one is already present - that's what makes
        every derived experiment comparable to what it came from without extra bookkeeping.
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
            steps=parent.steps if carry_steps else (),
        )
        if not any(r.role == "baseline" for r in builder.references):
            builder.add_reference(role="baseline", experiment_id=parent.id, label=f"parent: {parent.title}")
        return builder

    def merge(
        self,
        ref_a: str,
        ref_b: str,
        *,
        title: str,
        intent: str,
        take_structure: Iterable[str] = (),
        take_steps: Iterable[str] = (),
        branch: str | None = None,
        author: str | None = None,
        hypothesis: str | None = None,
    ) -> ExperimentBuilder:
        """Merge two lines of work into one experiment - the equivalent of `git merge`, with
        manual conflict resolution: ``take_structure``/``take_steps`` list the paths (in the
        format :meth:`diff`/:meth:`diff_steps` report) whose value should come from ``ref_b``
        instead of ``ref_a``; every path you don't list keeps ``ref_a``'s value. The result gets
        both tips as parents (so the graph records the merge like git does), carries over
        ``ref_a``'s other references (a ``target_spec`` pointer, say - the same "carry what came
        before" behaviour as :meth:`derive`), and adds a reference back to each side (``baseline``
        for ``ref_a``, ``merge_source`` for ``ref_b``).

        Both experiments must share the same ``structure_type`` - Follow does not attempt to
        reconcile two different domain schemas, and raises rather than silently producing a
        merge commit that mixes two unrelated domains.
        """
        a, b = self.get(ref_a), self.get(ref_b)
        if a.id == b.id:
            raise ValueError(f"{ref_a!r} and {ref_b!r} both resolve to {a.id} - nothing to merge")
        if a.structure_type != b.structure_type:
            raise ValueError(
                f"cannot merge {ref_a!r} ({a.structure_type}) with {ref_b!r} ({b.structure_type}): "
                "different structure types - Follow does not reconcile different domain schemas"
            )
        structure_cls = Structure.resolve(a.structure_type)

        merged_structure = resolve_merge_paths(
            self.load_structure(a).model_dump(mode="json"),
            self.load_structure(b).model_dump(mode="json"),
            take_structure,
        )
        merged_steps = resolve_merge_paths(
            [s.model_dump(mode="json") for s in a.steps],
            [s.model_dump(mode="json") for s in b.steps],
            take_steps,
        )

        carried_references = [r for r in a.references if r.role not in ("baseline", "merge_source")]

        builder = ExperimentBuilder(
            self,
            branch=branch or a.branch,
            parents=[a.id, b.id],
            structure=structure_cls.model_validate(merged_structure),
            title=title,
            intent=intent,
            author=author,
            hypothesis=hypothesis,
            objectives=a.objectives,
            references=carried_references,
            steps=[Step.model_validate(s) for s in merged_steps],
        )
        builder.add_reference(role="baseline", experiment_id=a.id, label=f"{a.branch}: {a.title}")
        builder.add_reference(role="merge_source", experiment_id=b.id, label=f"{b.branch}: {b.title}")
        return builder

    def load_draft(self, payload: dict[str, Any]) -> ExperimentBuilder:
        """Rebuild an :class:`ExperimentBuilder` from a draft dict produced by
        :meth:`ExperimentBuilder.to_draft`. ``payload["structure_type"]`` must already be
        registered (i.e. its module has been imported) or :class:`KeyError` is raised.
        """
        structure_cls = Structure.resolve(payload["structure_type"])
        builder = ExperimentBuilder(
            self,
            branch=payload["branch"],
            parents=list(payload.get("parents", [])),
            structure=structure_cls.model_validate(payload["structure"]),
            title=payload["title"],
            intent=payload["intent"],
            author=payload.get("author"),
            hypothesis=payload.get("hypothesis"),
            references=[ReferenceLink.model_validate(r) for r in payload.get("references", [])],
            objectives=[Objective.model_validate(o) for o in payload.get("objectives", [])],
            steps=[Step.model_validate(s) for s in payload.get("steps", [])],
            tags=list(payload.get("tags", [])),
            metadata=dict(payload.get("metadata", {})),
        )
        builder.evidence = [Evidence.model_validate(e) for e in payload.get("evidence", [])]
        if payload.get("conclusion"):
            builder.conclusion = Conclusion.model_validate(payload["conclusion"])
        return builder

    def branch(self, name: str, at: str) -> None:
        """Point branch ``name`` at the experiment resolved by ``at`` (id, branch, or tag)."""
        resolved = self._resolve_ref(at)
        self._ensure_branch_name_available(name)
        self._branches[name] = resolved
        if self.path is not None:
            self._persist_refs()

    def tag(self, name: str, at: str, *, force: bool = False) -> None:
        """Point tag ``name`` (an immutable label) at the experiment resolved by ``at``.

        Raises if ``name`` already tags a *different* experiment - tags are meant to be a
        stable, citable reference, so silently repointing one defeats the point. Pass
        ``force=True`` if you deliberately want to move it anyway.
        """
        resolved = self._resolve_ref(at)
        self._ensure_tag_assignment(name, resolved, force=force)
        self._tags[name] = resolved
        if self.path is not None:
            self._persist_refs()

    def _commit(self, builder: ExperimentBuilder) -> Experiment:
        for parent_id in builder.parents:
            if parent_id not in self._objects:
                raise ExperimentNotFoundError(parent_id)
        for reference in builder.references:
            # unlike external_source, experiment_id always means "an experiment in this
            # repository" - a dangling one would silently disappear everywhere it's used
            # (render_fiche's baseline diff, follow report's lineage section, ...) with no
            # indication anything was wrong, so it's rejected here rather than at every call site.
            if reference.experiment_id is not None and reference.experiment_id not in self._objects:
                raise ExperimentNotFoundError(reference.experiment_id)
        self._ensure_branch_name_available(builder.branch)

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
        current_tip_id = self._branches.get(builder.branch)
        if current_tip_id is not None:
            current_tip = self._objects[current_tip_id]
            # Ignoring id/created_at, is this commit identical to the branch's current tip? Then
            # there is nothing to commit - exactly like `git commit` with no staged changes,
            # this is refused rather than silently creating a content-duplicate commit (which
            # would orphan the existing tip: still in the repository, but no longer reachable
            # via log() once the branch moves past it) or silently doing nothing.
            unchanged = provisional.model_dump(mode="json", exclude={"id", "created_at"})
            if unchanged == current_tip.model_dump(mode="json", exclude={"id", "created_at"}):
                raise NothingToCommitError(builder.branch, current_tip_id)
            # The branch has moved on since builder.parents was decided (someone else committed
            # to it, or this builder derived from something other than the current tip - e.g.
            # `derive(<an old commit>, ...)` without new_branch, git's detached-HEAD situation).
            # Committing anyway would silently strand the current tip: still in the repository,
            # but unreachable via log() once the branch pointer moves past it.
            if current_tip_id not in builder.parents:
                raise FollowError(
                    f"branch {builder.branch!r} already points at {current_tip_id}, which is not "
                    f"among this commit's parents {builder.parents!r} - committing would abandon "
                    f"that history; derive from {current_tip_id!r} to continue this branch, or "
                    "commit to a new/different branch name instead"
                )

        payload = provisional.model_dump(mode="json", exclude={"id"})
        experiment = provisional.model_copy(update={"id": content_id("experiment", payload)})

        for tag in experiment.tags:
            self._ensure_tag_assignment(tag, experiment.id, force=False)

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
