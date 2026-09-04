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


def test_evidence_kind_defaults_to_standard_with_empty_narrative_and_typed_fields():
    evidence = Evidence(id="ev1", description="photo", source="file:///x")
    assert evidence.kind == "standard"
    assert evidence.objective is None
    assert evidence.interpretation is None
    assert evidence.graph_config is None
    assert evidence.image_annotations == []


def test_evidence_narrative_and_typed_fields_round_trip_through_json():
    image_evidence = Evidence(
        id="ev2",
        description="SEM du bord",
        source="file:///sem.png",
        kind="image",
        objective="Isolation electrique",
        interpretation="Le defaut observe explique la fuite mesuree",
        image_annotations=[{"attachment_id": "att_1", "type": "arrow", "x": 10.0, "y": 20.0, "x2": 15.0, "y2": 25.0, "label": "defaut ici"}],
    )
    restored = Evidence.model_validate(image_evidence.model_dump(mode="json"))
    assert restored == image_evidence
    assert restored.image_annotations[0]["label"] == "defaut ici"

    graph_evidence = Evidence(
        id="ev3",
        description="Split vs PL",
        source="—",
        kind="graph",
        graph_config={"title": "Split vs PL", "x_label": "Epaisseur (nm)", "y_label": "Intensite PL", "query": "TODO", "data_source_url": None},
    )
    restored_graph = Evidence.model_validate(graph_evidence.model_dump(mode="json"))
    assert restored_graph == graph_evidence
    assert restored_graph.graph_config["query"] == "TODO"


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
