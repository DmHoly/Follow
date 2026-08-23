from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .quantity import Quantity


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Objective(BaseModel):
    """One thing this experiment is trying to achieve or find out, expressed as a testable target."""

    name: str
    metric: str  # key used to look this up in Evidence.metrics / ObjectiveResult.observed
    direction: Literal["maximize", "minimize", "target", "range", "observe"] = "observe"
    target: float | None = None
    tolerance: float | None = None
    range: tuple[float, float] | None = None
    rationale: str | None = None


class Step(BaseModel):
    """One step of the experimental protocol. Steps are ordered but may depend on earlier ones."""

    order: int
    name: str
    description: str | None = None
    parameters: dict[str, Quantity] = Field(default_factory=dict)
    duration: str | None = None
    depends_on: list[int] = Field(default_factory=list)


class ReferenceLink(BaseModel):
    """A point of comparison for this experiment: a baseline, a control, prior art, a spec.

    Unlike ``parents`` (which record lineage - "this config was derived from that one"),
    a reference is purely about comparison and does not have to be an ancestor: you can point
    at a sibling branch, an old champion, or an external literature value.
    """

    role: Literal["baseline", "control", "prior_art", "benchmark", "target_spec", "merge_source"]
    label: str
    experiment_id: str | None = None
    external_source: str | None = None
    note: str | None = None


class Evidence(BaseModel):
    """A pointer to data that backs this experiment. Follow never owns or stores the data itself,
    only a reference to it (a path, URI, or DOI), what it claims to show, and optionally a
    checksum so the reference can later be verified against the actual file.
    """

    id: str
    description: str
    source: str
    checksum: str | None = None
    metrics: dict[str, Quantity] = Field(default_factory=dict)
    collected_at: datetime | None = None


class ObjectiveResult(BaseModel):
    """The verdict on one Objective, and the evidence/reasoning that supports it."""

    objective: str  # Objective.name
    status: Literal["met", "not_met", "partially_met", "inconclusive"]
    observed: Quantity | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    reasoning: str | None = None


class Conclusion(BaseModel):
    """The outcome of the experiment: per-objective verdicts, a narrative, and what to do next."""

    status: Literal["draft", "running", "concluded", "abandoned"] = "draft"
    objective_results: list[ObjectiveResult] = Field(default_factory=list)
    summary: str | None = None
    decision: Literal["promote", "branch", "replicate", "abandon", "inconclusive"] | None = None
    decided_at: datetime | None = None


class Experiment(BaseModel):
    """One immutable, committed node in the experiment graph - the equivalent of a git commit.

    Its id is derived from its own content (see :mod:`follow.ids`), its ``parents`` record
    lineage (what it was derived from, possibly several for a merge of two lines of work), and
    ``structure_type`` is the registry key needed to rehydrate ``structure`` back into the right
    :class:`~follow.structure.Structure` subclass.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    parents: list[str] = Field(default_factory=list)
    branch: str
    created_at: datetime = Field(default_factory=_utcnow)
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

    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
