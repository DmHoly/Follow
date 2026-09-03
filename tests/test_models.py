"""Regression tests: Step/Objective/ReferenceLink/Evidence/ObjectiveResult/Conclusion must be
frozen, otherwise mutating one in place on a derived ExperimentBuilder (a very natural mistake -
`builder.steps[0].name = "..."` reads like the obvious way to edit a mutable Python object)
silently corrupts the same object still referenced by an already-committed, supposedly immutable
parent Experiment, since derive()/merge() only shallow-copy the *list*, not its elements.
"""

import pytest
from pydantic import ValidationError

from follow import Conclusion, Evidence, Objective, ObjectiveResult, Quantity, ReferenceLink, Step


def test_step_is_frozen():
    step = Step(order=1, name="Mix")
    with pytest.raises(ValidationError):
        step.name = "Mutated"


def test_objective_is_frozen():
    objective = Objective(name="Rise", metric="height_cm")
    with pytest.raises(ValidationError):
        objective.target = 5.0


def test_reference_link_is_frozen():
    reference = ReferenceLink(role="baseline", label="parent", experiment_id="exp_abc")
    with pytest.raises(ValidationError):
        reference.label = "mutated"


def test_evidence_is_frozen():
    evidence = Evidence(id="ev1", description="photo", source="file:///x")
    with pytest.raises(ValidationError):
        evidence.description = "mutated"


def test_evidence_step_index_defaults_to_none_and_round_trips_when_set():
    without_step = Evidence(id="ev1", description="photo", source="file:///x")
    assert without_step.step_index is None

    with_step = Evidence(id="ev2", description="mesure de perf", source="file:///y", step_index=2)
    assert with_step.step_index == 2
    assert Evidence.model_validate(with_step.model_dump(mode="json")).step_index == 2


def test_objective_result_is_frozen():
    result = ObjectiveResult(objective="Rise", status="met")
    with pytest.raises(ValidationError):
        result.status = "not_met"


def test_conclusion_is_frozen():
    conclusion = Conclusion(status="concluded")
    with pytest.raises(ValidationError):
        conclusion.status = "abandoned"


def test_mutating_a_shared_step_instance_is_now_a_loud_error_not_silent_corruption():
    # A derived builder's steps list is a shallow copy of the parent's - the Step *instances*
    # are shared until one is actually replaced via .model_copy(). Frozen Step turns an
    # attempted in-place edit into an immediate error instead of corrupting the parent.
    shared_step = Step(order=1, name="Cuire")
    parent_steps = [shared_step]
    child_steps = list(parent_steps)  # exactly what ExperimentBuilder.__init__ does

    with pytest.raises(ValidationError):
        child_steps[0].name = "Cuire plus longtemps"

    assert parent_steps[0].name == "Cuire"  # untouched

    # the correct idiom still works and does not affect the parent's list
    child_steps[0] = child_steps[0].model_copy(update={"name": "Cuire plus longtemps"})
    assert parent_steps[0].name == "Cuire"
    assert child_steps[0].name == "Cuire plus longtemps"


def test_quantity_was_already_frozen():
    q = Quantity(value=1, unit="g")
    with pytest.raises(ValidationError):
        q.value = 2
