"""Deliberate misuse of the core engine: each test tries to do something a user could plausibly
attempt by mistake, and checks it now fails loudly and clearly instead of silently corrupting
state or crashing with a confusing low-level error. Every one of these was reproduced as a real,
silent problem before the corresponding fix.
"""

import pytest
from pydantic import ValidationError

from examples.mosfet import Layer, MOSFETStructure
from examples.recipe import BakeStep, CakeRecipe
from follow import ExperimentNotFoundError, FollowError, Quantity, ReferenceLink, Repository
from follow.merging import split_path


def _cake(flour_g: float = 200) -> CakeRecipe:
    return CakeRecipe(
        name="Vanilla cake",
        ingredients={"flour": Quantity(value=flour_g, unit="g")},
        bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def _mosfet() -> MOSFETStructure:
    return MOSFETStructure(
        gate_length=Quantity(value=45, unit="nm"),
        gate_oxide=Layer(material="HfO2", thickness=Quantity(value=2, unit="nm")),
        channel_doping=Quantity(value=1e17, unit="cm^-3"),
        source=Layer(material="Si:P", thickness=Quantity(value=50, unit="nm")),
        drain=Layer(material="Si:P", thickness=Quantity(value=50, unit="nm")),
    )


def test_repointing_an_existing_tag_is_rejected_without_force():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    v2 = repo.new(branch="main", structure=_cake(), title="v2", intent="x", parents=[v1.id]).commit()
    repo.tag("release", v1.id)

    with pytest.raises(FollowError, match="immutable"):
        repo.tag("release", v2.id)
    assert repo.tags["release"] == v1.id  # unchanged

    # re-tagging the SAME target is fine (idempotent), no force needed
    repo.tag("release", v1.id)
    assert repo.tags["release"] == v1.id

    # force=True is the explicit escape hatch
    repo.tag("release", v2.id, force=True)
    assert repo.tags["release"] == v2.id


def test_committing_with_a_dangling_parent_id_is_rejected():
    repo = Repository()
    with pytest.raises(ExperimentNotFoundError):
        repo.new(branch="main", structure=_cake(), title="v1", intent="x", parents=["exp_does_not_exist"]).commit()
    assert len(repo) == 0  # nothing partially committed


def test_branch_name_colliding_with_an_existing_tag_is_rejected():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    repo.tag("v1-release", v1.id)

    with pytest.raises(FollowError, match="namespace"):
        repo.new(branch="v1-release", structure=_cake(), title="v2", intent="x", parents=[v1.id]).commit()
    assert "v1-release" not in repo.branches


def test_tag_name_colliding_with_an_existing_branch_is_rejected():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()

    with pytest.raises(FollowError, match="namespace"):
        repo.tag("main", v1.id)


def test_continuing_an_existing_branch_is_not_a_collision():
    # the branch-name guard must only fire for a genuinely NEW name, not routine continuation
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    v2 = repo.derive(v1.id, title="v2", intent="x").commit()
    assert repo.branches["main"] == v2.id


def test_merging_across_domains_is_rejected():
    repo = Repository()
    recipe = repo.new(branch="recipe", structure=_cake(), title="recipe", intent="x").commit()
    mosfet = repo.new(branch="mosfet", structure=_mosfet(), title="mosfet", intent="x").commit()

    with pytest.raises(ValueError, match="different structure types"):
        repo.merge("recipe", "mosfet", title="oops", intent="x")


def test_malformed_bracket_index_is_rejected_not_silently_misparsed():
    with pytest.raises(ValueError, match="malformed path"):
        split_path("steps[abc].name")
    with pytest.raises(ValueError, match="malformed path"):
        split_path("steps[2.name")  # unclosed bracket


def test_recommitting_the_same_builder_is_rejected():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    first = builder.commit()

    builder.add_evidence(id="ev1", description="forgot this", source="file:///x")
    with pytest.raises(FollowError, match="already committed"):
        builder.commit()

    # the first commit is untouched, and remains the branch tip - no orphaned sibling appeared
    assert repo.branches["main"] == first.id
    assert len(repo) == 1


def test_merge_path_not_found_names_the_full_path_not_just_the_missing_key():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    branch = repo.derive(v1.id, new_branch="feature", title="feature", intent="x")
    branch.structure.ingredients["flour"] = Quantity(value=240, unit="g")
    tip = branch.commit()

    with pytest.raises(KeyError, match="ingredients.typo"):
        repo.merge("main", tip.id, title="m", intent="x", take_structure=["ingredients.typo"]).commit()


def test_objective_result_referencing_an_unknown_objective_is_rejected():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_objective(name="Rise", metric="height_cm", direction="maximize", target=5.0)
    builder.conclude(status="concluded", objective_results=[{"objective": "Ryse", "status": "met"}])  # typo

    with pytest.raises(ValidationError, match="Ryse"):
        builder.commit()


def test_reference_link_without_a_target_is_rejected():
    with pytest.raises(ValidationError, match="needs a target"):
        ReferenceLink(role="baseline", label="empty")

    # either target on its own is fine
    ReferenceLink(role="baseline", label="internal", experiment_id="exp_abc")
    ReferenceLink(role="prior_art", label="paper", external_source="doi://10.1/x")


def test_recommitting_an_unchanged_draft_is_an_idempotent_no_op():
    # a fresh builder (as load_draft() would produce from an unmodified file on disk) whose
    # content exactly matches the branch tip must not create a duplicate/orphan.
    repo = Repository()
    first = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()

    again = repo.new(branch="main", structure=_cake(), title="v1", intent="x", parents=[]).commit()

    assert again.id == first.id
    assert len(repo) == 1
    assert repo.branches["main"] == first.id


def test_a_genuinely_different_commit_on_the_same_branch_is_not_treated_as_a_no_op():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    v2 = repo.derive(v1.id, title="v2", intent="different").commit()

    assert v2.id != v1.id
    assert len(repo) == 2


def test_duplicate_step_order_is_rejected():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_step(name="A", order=1)
    builder.add_step(name="B", order=1)

    with pytest.raises(ValidationError, match="order=1"):
        builder.commit()


def test_depends_on_referencing_an_unknown_step_order_is_rejected():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_step(name="A", depends_on=[99])

    with pytest.raises(ValidationError, match="depends_on"):
        builder.commit()


def test_depends_on_referencing_a_real_step_is_fine():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_step(name="A")
    builder.add_step(name="B", depends_on=[1])
    committed = builder.commit()
    assert committed.steps[1].depends_on == [1]
