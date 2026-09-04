from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .quantity import Quantity


def utcnow() -> datetime:
    """Now, in UTC. Shared so the models and the repository cannot drift onto two clocks."""
    return datetime.now(timezone.utc)


class Objective(BaseModel):
    """One thing this experiment is trying to achieve or find out, expressed as a testable target."""

    model_config = ConfigDict(frozen=True)

    name: str
    metric: str  # key used to look this up in Evidence.metrics / ObjectiveResult.observed
    direction: Literal["maximize", "minimize", "target", "range", "observe"] = "observe"
    target: float | None = None
    tolerance: float | None = None
    range: tuple[float, float] | None = None
    rationale: str | None = None


class Step(BaseModel):
    """One step of the experimental protocol. Steps are ordered but may depend on earlier ones."""

    model_config = ConfigDict(frozen=True)

    order: int
    name: str
    description: str | None = None
    parameters: dict[str, Quantity] = Field(default_factory=dict)
    duration: str | None = None
    depends_on: list[int] = Field(default_factory=list)


def steps_by_order(steps: "Iterable[Step]") -> dict[str, Any]:
    """A protocol keyed by each step's ``order``, which is what diffing and merging compare on.

    Comparing two protocols position by position - the natural thing to do with two lists - is
    only correct while both sides have the same steps in the same slots. Insert one step at the
    top of a protocol and every later step shifts: the diff claims each one changed, and
    ``--take-steps "[2]"`` quietly imports the step next to the intended one. ``order`` is the
    identity a step already carries (it is what the fiche numbers it by, and it is validated
    unique), so keying on it makes an insertion show up as exactly one added step.

    Keys are the order as a string, so a path reads ``3.parameters.temperature``: the 3 is the
    step number a reader sees in the fiche, not an offset into a list.
    """
    return {str(step.order): step.model_dump(mode="json") for step in steps}


class ReferenceLink(BaseModel):
    """A point of comparison for this experiment: a baseline, a control, prior art, a spec.

    Unlike ``parents`` (which record lineage - "this config was derived from that one"),
    a reference is purely about comparison and does not have to be an ancestor: you can point
    at a sibling branch, an old champion, or an external literature value.
    """

    model_config = ConfigDict(frozen=True)

    role: Literal["baseline", "control", "prior_art", "benchmark", "target_spec", "merge_source"]
    label: str
    experiment_id: str | None = None
    external_source: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _check_has_a_target(self) -> "ReferenceLink":
        if self.experiment_id is None and self.external_source is None:
            raise ValueError(
                "a reference needs a target: set experiment_id (another experiment in this "
                "repository) or external_source (a URL/DOI/citation outside it) - otherwise it's "
                "just a floating label pointing at nothing"
            )
        return self


class Evidence(BaseModel):
    """A pointer to data that backs this experiment. Follow never owns or stores the data itself,
    only a reference to it (a path, URI, or DOI), what it claims to show, and optionally a
    checksum so the reference can later be verified against the actual file.

    ``step_index`` optionally anchors this evidence to a point in the experiment's own protocol
    (``Experiment.steps``) - e.g. a characterization measurement taken right after a specific
    process step, rather than a general end-of-experiment result. Follow stays decoupled from
    whatever step model a caller actually uses (StructureForge or otherwise): this is a bare,
    caller-interpreted index, not validated or resolved here.

    ``kind`` distinguishes a plain measurement from richer forms a caller may build a dedicated
    editor/renderer for - ``"image"`` (a picture, optionally with ``image_annotations`` marking it
    up) or ``"graph"`` (a plot described by ``graph_config``). ``objective`` optionally names one
    of the experiment's own ``Objective``s this evidence speaks to, and ``interpretation`` is the
    free-text "why this result makes sense given the change" a caller may want next to it -
    together the intent is that a piece of evidence tells the whole small story (what changed, for
    which goal, what was observed, why it's consistent) rather than just carrying a bare number.
    Like ``step_index``, all of this is caller-interpreted: Follow stores it and validates nothing
    about its shape beyond the bare field types, deliberately staying ignorant of what a "graph" or
    an "image annotation" actually is to whichever tool renders them.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    source: str
    checksum: str | None = None
    kind: Literal["standard", "image", "graph"] = "standard"
    objective: str | None = None
    interpretation: str | None = None
    graph_config: dict[str, Any] | None = None
    image_annotations: list[dict[str, Any]] = Field(default_factory=list)
    step_index: int | None = None
    metrics: dict[str, Quantity] = Field(default_factory=dict)
    collected_at: datetime | None = None


class ObjectiveResult(BaseModel):
    """The verdict on one Objective, and the evidence/reasoning that supports it."""

    model_config = ConfigDict(frozen=True)

    objective: str  # Objective.name
    status: Literal["met", "not_met", "partially_met", "inconclusive"]
    observed: Quantity | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    reasoning: str | None = None


class Conclusion(BaseModel):
    """The outcome of the experiment: per-objective verdicts, a narrative, and what to do next."""

    model_config = ConfigDict(frozen=True)

    status: Literal["draft", "running", "concluded", "abandoned"] = "draft"
    objective_results: list[ObjectiveResult] = Field(default_factory=list)
    summary: str | None = None
    decision: Literal["promote", "branch", "replicate", "abandon", "inconclusive"] | None = None
    next_steps: str | None = None
    decided_at: datetime | None = None


class Experiment(BaseModel):
    """One immutable, committed node in the experiment graph - the equivalent of a git commit.

    Its id is derived from its own content (see :mod:`follow.core.ids`), its ``parents`` record
    lineage (what it was derived from, possibly several for a merge of two lines of work), and
    ``structure_type`` is the registry key needed to rehydrate ``structure`` back into the right
    :class:`~follow.core.structure.Structure` subclass.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    parents: list[str] = Field(default_factory=list)
    branch: str
    created_at: datetime = Field(default_factory=utcnow)
    author: str | None = None

    title: str
    intent: str
    hypothesis: str | None = None

    structure_type: str
    structure: dict[str, Any]

    references: list[ReferenceLink] = Field(default_factory=list)
    objectives: list[Objective] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    conclusion: Conclusion = Field(default_factory=Conclusion)

    # free-form descriptive labels ("à refaire", "pilote", "campagne-Q3"), the same
    # never-validated spirit as `metadata`. Deliberately NOT repository tags: several experiments
    # may carry the same label, and none of them creates a ref. A citable, immutable pointer to
    # one experiment is a repository tag, created explicitly with
    # :meth:`Repository.tag <follow.storage.repository.Repository.tag>`.
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # answers to the repository's commit form (follow.storage.commit_form), if one was configured -
    # validated at commit time, unlike `metadata` which is never checked against anything.
    form_answers: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_objective_results_reference_real_objectives(self) -> "Experiment":
        known = {o.name for o in self.objectives}
        for result in self.conclusion.objective_results:
            if result.objective not in known:
                raise ValueError(
                    f"conclusion references objective {result.objective!r}, which is not one of "
                    f"this experiment's objectives ({sorted(known)!r}) - check for a typo, or add "
                    "the objective before concluding on it"
                )
        return self

    @model_validator(mode="after")
    def _check_steps_are_well_formed(self) -> "Experiment":
        orders = [s.order for s in self.steps]
        seen: set[int] = set()
        for order in orders:
            if order in seen:
                raise ValueError(
                    f"two steps both have order={order} - step order must be unique so the "
                    "protocol has one unambiguous sequence (add_step() sets it automatically; "
                    "pass order= explicitly only if you need to override that)"
                )
            seen.add(order)
        known_orders = set(orders)
        for step in self.steps:
            unknown = [d for d in step.depends_on if d not in known_orders]
            if unknown:
                raise ValueError(
                    f"step {step.order} ({step.name!r}) depends_on={unknown}, which "
                    f"{'is not an' if len(unknown) == 1 else 'are not'} order of any step in this "
                    "experiment - check for a typo"
                )
        return self
