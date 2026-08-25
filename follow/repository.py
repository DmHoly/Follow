from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Iterator

from .commit_form import CommitForm, load_commit_form
from .diffing import StructureDiff, diff_structures
from .entities import find_entity_mentions
# re-exported here so `from follow.repository import FollowError` keeps working
from .errors import (  # noqa: F401
    DanglingRefError,
    ExperimentNotFoundError,
    FollowError,
    MergeError,
    NothingToCommitError,
)
from .ids import content_id
from .merging import resolve_merge_paths
from .models import Conclusion, Evidence, Experiment, Objective, ReferenceLink, Step, steps_by_order, utcnow
from .storage import JsonFileStore, MemoryStore, ObjectStore
from .structure import Structure


def _step_order_key(entry: Any) -> tuple[int, str]:
    """Sort step-diff entries by step number, not by the string form of the path.

    The paths are keyed by ``order`` as a string, so plain sorting would read 1, 10, 11, 2 - the
    diff of a ten-step protocol would be listed out of protocol order.
    """
    head, _, rest = entry.path.partition(".")
    return (int(head) if head.isdigit() else 0, rest)


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
        form_answers: dict[str, Any] | None = None,
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
        self.form_answers: dict[str, Any] = dict(form_answers or {})
        self._committed = False

    def add_objective(self, **kwargs: Any) -> "ExperimentBuilder":
        self.objectives.append(Objective(**kwargs))
        return self

    def add_reference(self, **kwargs: Any) -> "ExperimentBuilder":
        self.references.append(ReferenceLink(**kwargs))
        return self

    def add_step(self, **kwargs: Any) -> "ExperimentBuilder":
        """Append a protocol step, numbering it after the highest ``order`` already present.

        Counting the steps instead (``len(self.steps) + 1``) collided the moment any order was
        set by hand or inherited non-contiguously: ``add_step(order=2)`` followed by a plain
        ``add_step()`` produced two steps both claiming order 2, and nothing said so until
        :meth:`commit` ran the validator, far from the call that caused it.
        """
        kwargs.setdefault("order", max((s.order for s in self.steps), default=0) + 1)
        self.steps.append(Step(**kwargs))
        return self

    def add_evidence(self, **kwargs: Any) -> "ExperimentBuilder":
        self.evidence.append(Evidence(**kwargs))
        return self

    def answer_form(self, **answers: Any) -> "ExperimentBuilder":
        """Record answers to the repository's commit form (see :mod:`follow.commit_form`).
        Merges into any answers already set - call it more than once to fill the form
        incrementally. Not validated until :meth:`commit`, so a typo'd field name only shows up
        as an error there (alongside every other problem, not just this one).
        """
        self.form_answers.update(answers)
        return self

    def conclude(self, **kwargs: Any) -> "ExperimentBuilder":
        kwargs.setdefault("status", "concluded")
        kwargs.setdefault("decided_at", utcnow())
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

        If the repository has a commit form configured (see :mod:`follow.commit_form`),
        :attr:`form_answers` must satisfy it - see :meth:`answer_form`. A repository with no
        commit form configured accepts whatever ``form_answers`` were set (or none at all)
        without validating them.
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
            "form_answers": self.form_answers,
        }


class Repository:
    """A store of experiments and the branches/tags pointing into their lineage - Follow's
    equivalent of a git repository. Experiments are content-addressed and immutable once
    committed; branches are mutable pointers to the latest experiment on a line of work.

    Pass ``path`` to persist to plain JSON files (one per experiment, plus a refs file), or
    leave it out for an in-memory repository (handy for tests and notebooks). Pass ``store`` for
    anything else: a :class:`~follow.storage.ObjectStore` is the whole of what this class knows
    about persistence, so a different backend replaces one collaborator instead of editing the
    class that also holds the commit rules.

    Pass ``commit_form`` (a path to a YAML template, or an already-loaded
    :class:`~follow.commit_form.CommitForm`) to make answering it mandatory before any commit is
    accepted - see :mod:`follow.commit_form`. Left unset, a persisted repository still picks up
    ``<path>/commit_form.yml`` automatically if that file exists, so dropping one into an
    existing repository's directory is enough to start requiring it from then on.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        commit_form: str | Path | CommitForm | None = None,
        store: ObjectStore | None = None,
    ):
        if store is not None and path is not None:
            raise FollowError("pass either path= or store=, not both - a store already knows where it writes")
        self._store: ObjectStore = store if store is not None else (MemoryStore() if path is None else JsonFileStore(path))
        self.path = Path(path) if path is not None else None

        if isinstance(commit_form, CommitForm):
            self.commit_form: CommitForm | None = commit_form
        elif commit_form is not None:
            self.commit_form = load_commit_form(commit_form)
        else:
            self.commit_form = self._store.default_commit_form()

        self._objects, self._branches, self._tags = self._store.load()

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
        """Resolve a branch name, tag name or experiment id to an id that is actually stored.

        A ref is only resolved once its target has been confirmed present: returning the id a
        stale ``refs.json`` names, without checking, left ``get()`` to fail on a bare
        ``KeyError`` carrying nothing but a hash - and made ``ref in repo`` answer True for a
        ref that ``get()`` could not honour.
        """
        for kind, table in (("branch", self._branches), ("tag", self._tags)):
            if ref in table:
                target = table[ref]
                if target not in self._objects:
                    raise DanglingRefError(kind, ref, target)
                return target
        if ref in self._objects:
            return ref
        raise ExperimentNotFoundError(ref)

    def _stored(self, experiment_id: str, *, reached_from: str) -> Experiment:
        """One stored experiment by id, or a clear error naming what pointed at it."""
        try:
            return self._objects[experiment_id]
        except KeyError:
            raise DanglingRefError("parent of", reached_from, experiment_id) from None

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
        previous = ref
        while current and current not in seen:
            seen.add(current)
            exp = self._stored(current, reached_from=previous)
            history.append(exp)
            previous = exp.id
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
        compares their structure - use it to find the ``<order>``/``<order>.field`` paths to pass
        to :meth:`merge`'s ``take_steps``.

        Steps are matched on their :attr:`~follow.models.Step.order`, not on their position (see
        :func:`~follow.models.steps_by_order`), so inserting a step at the top of one protocol
        reports one added step rather than claiming every later step changed. A path therefore
        reads ``3.parameters.temperature``: the step *numbered* 3, the one the fiche shows as
        "3.", whichever slot it occupies in the list.
        """
        a, b = self.get(ref_a), self.get(ref_b)
        diff = diff_structures(steps_by_order(a.steps), steps_by_order(b.steps))
        return StructureDiff(entries=sorted(diff.entries, key=_step_order_key))

    def find_entity(self, entity_id: str) -> list[Experiment]:
        """Every experiment in this repository that mentions the physical entity
        ``entity_id`` (see :mod:`follow.entities`), oldest first.

        This crosses branches and git lineage entirely: an experiment naming
        ``entity_id="moule-vert"`` inside a batch, and a later, unrelated experiment that
        just happens to reuse the same string in its own structure, both come back here -
        no reference or parent link between them required. That's the point: name the
        physical thing once, and every experiment that later mentions it is found by that
        name alone, not by hand-maintained bookkeeping.
        """
        matches = [exp for exp in self._objects.values() if find_entity_mentions(exp.structure, entity_id)]
        matches.sort(key=lambda exp: exp.created_at)
        return matches

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

        ``tags`` are free-form descriptive labels stored on the experiment; they do not create
        repository tags, so the same label may be reused on as many experiments as you like. Use
        :meth:`tag` for a citable, immutable pointer to one specific experiment.
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
        to the parent is always added - that's what makes every derived experiment comparable to
        what it came from without extra bookkeeping.

        The parent's own lineage references (``baseline``, and ``merge_source`` when deriving from
        a merge commit) are deliberately *not* carried over: they describe where the *parent* came
        from, not this experiment, and keeping them would leave the new commit pointing its
        baseline at its grandparent - so :meth:`ExperimentBuilder.diff_from_baseline` and every
        "what changed versus the reference" view would silently compare against the wrong
        ancestor. Every other reference (a ``target_spec``, a ``prior_art`` citation...) is carried
        over as before, the same way :meth:`merge` does it.
        """
        parent = self.get(ref)
        carried_references = (
            [r for r in parent.references if r.role not in ("baseline", "merge_source")] if carry_references else ()
        )
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
            references=carried_references,
            steps=parent.steps if carry_steps else (),
        )
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
        instead of ``ref_a``; every path you don't list keeps ``ref_a``'s value. A ``take_steps``
        path names a step by its :attr:`~follow.models.Step.order` - ``"3"`` for the whole step
        numbered 3, ``"3.parameters.temperature"`` for one of its parameters - not by its slot in
        the list, so it keeps meaning the same step when the two protocols differ in length. The result gets
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
            raise MergeError(f"{ref_a!r} and {ref_b!r} both resolve to {a.id} - nothing to merge")
        if a.structure_type != b.structure_type:
            raise MergeError(
                f"cannot merge {ref_a!r} ({a.structure_type}) with {ref_b!r} ({b.structure_type}): "
                "different structure types - Follow does not reconcile different domain schemas"
            )
        structure_cls = Structure.resolve(a.structure_type)

        merged_structure = resolve_merge_paths(
            self.load_structure(a).model_dump(mode="json"),
            self.load_structure(b).model_dump(mode="json"),
            take_structure,
        )
        merged_steps = resolve_merge_paths(steps_by_order(a.steps), steps_by_order(b.steps), take_steps)

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
            steps=[Step.model_validate(s) for s in sorted(merged_steps.values(), key=lambda step: step["order"])],
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
            form_answers=dict(payload.get("form_answers", {})),
        )
        builder.evidence = [Evidence.model_validate(e) for e in payload.get("evidence", [])]
        if payload.get("conclusion"):
            builder.conclusion = Conclusion.model_validate(payload["conclusion"])
        return builder

    def _descends_from(self, ancestor_id: str, descendant_id: str) -> bool:
        """Is ``descendant_id`` ``ancestor_id`` itself, or one of its descendants?

        Walks *every* parent line, not just the first the way :meth:`log` does: a commit reached
        only through the second parent of a merge is still genuinely part of that history, and
        treating it as unrelated would refuse a move that loses nothing.
        """
        seen: set[str] = set()
        stack = [descendant_id]
        while stack:
            node = stack.pop()
            if node == ancestor_id:
                return True
            if node in seen:
                continue
            seen.add(node)
            experiment = self._objects.get(node)
            if experiment is not None:
                stack.extend(experiment.parents)
        return False

    def branch(self, name: str, at: str, *, force: bool = False) -> None:
        """Point branch ``name`` at the experiment resolved by ``at`` (id, branch, or tag).

        Creating a branch, or moving one forward onto a descendant of its current tip (git's
        fast-forward), is always allowed - nothing becomes unreachable. Moving one *sideways or
        backwards*, onto a commit its current tip does not descend from, would leave that tip
        stranded: still stored, but no longer reachable from any branch via :meth:`log`. That is
        the very thing :meth:`_commit` refuses to do, so it is refused here too, and needs the
        same kind of deliberate opt-in :meth:`tag` asks for: ``force=True``.
        """
        resolved = self._resolve_ref(at)
        self._ensure_branch_name_available(name)
        current_tip_id = self._branches.get(name)
        if (
            current_tip_id is not None
            and current_tip_id != resolved
            and not force
            and not self._descends_from(current_tip_id, resolved)
        ):
            raise FollowError(
                f"branch {name!r} points at {current_tip_id}, which {resolved} does not descend "
                f"from - moving it there would abandon that history (it would stay in the "
                f"repository but no longer be reachable from any branch); tag {current_tip_id!r} "
                "or point another branch at it first if you want to keep it, or pass force=True "
                "to move anyway"
            )
        self._branches[name] = resolved
        self._persist_refs()

    def tag(self, name: str, at: str, *, force: bool = False) -> None:
        """Point tag ``name`` (an immutable label) at the experiment resolved by ``at``.

        This is the only way a repository tag is created - an experiment's own ``tags`` field is
        just descriptive metadata and never becomes a ref (several experiments can share a label).

        Raises if ``name`` already tags a *different* experiment - tags are meant to be a
        stable, citable reference, so silently repointing one defeats the point. Pass
        ``force=True`` if you deliberately want to move it anyway.
        """
        resolved = self._resolve_ref(at)
        self._ensure_tag_assignment(name, resolved, force=force)
        self._tags[name] = resolved
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

        # a repository with a commit form configured requires every commit to answer it - the
        # same idea as a required PR template, enforced instead of merely suggested.
        form_answers = self.commit_form.validate_answers(builder.form_answers) if self.commit_form is not None else dict(builder.form_answers)

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
            form_answers=form_answers,
        )
        current_tip_id = self._branches.get(builder.branch)
        if current_tip_id is not None:
            current_tip = self._stored(current_tip_id, reached_from=builder.branch)
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

        # The id is derived from what the experiment *says*, not from when it was written:
        # created_at is excluded, exactly like the NothingToCommitError comparison above already
        # does. Hashing it in made every id depend on the clock, so the same content committed
        # twice produced two unrelated ids - which is the opposite of what content addressing is
        # for, and quietly falsified content_id's promise that identical payloads dedupe.
        payload = provisional.model_dump(mode="json", exclude={"id", "created_at"})
        experiment = provisional.model_copy(update={"id": content_id("experiment", payload)})

        # Content addressing means an id already in the store denotes this exact content, so the
        # commit that is already there wins - re-storing would only overwrite its created_at,
        # rewriting an object the repository promises is immutable. This is git's dedupe rule.
        stored = self._objects.get(experiment.id)
        if stored is not None:
            experiment = stored
        else:
            self._objects[experiment.id] = experiment

        # Experiment.tags are free-form descriptive labels, like `metadata` - deliberately NOT
        # repository tags. Promoting them to refs made a second experiment reusing an ordinary
        # label ("important", "à refaire") fail its commit outright, with a message about
        # repo.tag() the user had never called: one field cannot be both a throwaway label and an
        # immutable citable pointer. Repository tags are created explicitly, via repo.tag().
        self._branches[experiment.branch] = experiment.id

        self._store.add_experiment(experiment)
        self._persist_refs()
        return experiment

    # -- persistence -----------------------------------------------------------------
    #
    # Nothing here decides *how* anything is stored - see follow.storage. What is left is when:
    # an experiment is written once, on commit; the refs whenever a pointer moves.

    def _persist_refs(self) -> None:
        self._store.write_refs(self._branches, self._tags)
