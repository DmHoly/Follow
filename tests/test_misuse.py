"""Deliberate misuse of the core engine: each test tries to do something a user could plausibly
attempt by mistake, and checks it now fails loudly and clearly instead of silently corrupting
state or crashing with a confusing low-level error. Every one of these was reproduced as a real,
silent problem before the corresponding fix.
"""

import pytest
from pydantic import ValidationError

from examples.mosfet import Layer, MOSFETStructure
from examples.recipe import BakeStep, CakeRecipe
from follow import ExperimentNotFoundError, FollowError, NothingToCommitError, Quantity, ReferenceLink, Repository
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


def test_recommitting_an_unchanged_draft_is_refused_like_git_commit_with_nothing_staged():
    # a fresh builder (as load_draft() would produce from an unmodified file on disk) whose
    # content exactly matches the branch tip must not create a duplicate/orphan - and, like
    # `git commit` with nothing staged, it should refuse rather than silently doing nothing.
    repo = Repository()
    first = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()

    again = repo.new(branch="main", structure=_cake(), title="v1", intent="x", parents=[])
    with pytest.raises(NothingToCommitError, match="nothing to commit"):
        again.commit()

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


def test_deriving_into_an_existing_unrelated_branch_name_does_not_abandon_its_history():
    repo = Repository()
    a1 = repo.new(branch="feature", structure=_cake(), title="feature-v1", intent="x").commit()
    a2 = repo.derive(a1.id, title="feature-v2", intent="x").commit()
    b1 = repo.new(branch="other", structure=_cake(), title="other-v1", intent="x").commit()

    with pytest.raises(FollowError, match="abandon"):
        repo.derive(b1.id, new_branch="feature", title="oops", intent="x").commit()

    # "feature" is untouched - still points at a2, its real history is intact
    assert repo.branches["feature"] == a2.id
    assert [e.id for e in repo.log("feature")] == [a2.id, a1.id]


def test_deriving_from_a_non_tip_commit_without_a_new_branch_is_rejected():
    # deriving from history rather than the branch's current tip, while staying "on" that same
    # branch name, is git's detached-HEAD situation - it must not silently rewrite the branch.
    repo = Repository()
    a1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    a2 = repo.derive(a1.id, title="v2", intent="x").commit()
    a3 = repo.derive(a2.id, title="v3", intent="x").commit()

    with pytest.raises(FollowError, match="abandon"):
        repo.derive(a1.id, title="v2-bis", intent="x").commit()

    assert repo.branches["main"] == a3.id
    assert [e.id for e in repo.log("main")] == [a3.id, a2.id, a1.id]

    # the escape hatch: an explicit new_branch is always allowed, exactly like `git checkout -b`
    fork = repo.derive(a1.id, new_branch="fork-from-v1", title="fork", intent="x").commit()
    assert repo.branches["fork-from-v1"] == fork.id


def test_merge_target_branch_moving_before_commit_is_rejected_not_silently_stale():
    # if the target branch advances between building the merge and committing it (e.g. another
    # commit landed in between), committing the stale merge must not silently strand the new tip.
    repo = Repository()
    a1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    branch = repo.derive(a1.id, new_branch="side", title="side", intent="x")
    branch.structure.ingredients["flour"] = Quantity(value=999, unit="g")
    side_tip = branch.commit()

    merge_builder = repo.merge("main", side_tip.id, title="merge", intent="x")
    # main advances past a1 before the merge above is actually committed
    a2 = repo.derive(a1.id, title="v2", intent="x").commit()

    with pytest.raises(FollowError, match="abandon"):
        merge_builder.commit()

    assert repo.branches["main"] == a2.id


def test_dangling_reference_experiment_id_is_rejected():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_reference(role="baseline", label="ghost", experiment_id="exp_does_not_exist")

    with pytest.raises(ExperimentNotFoundError):
        builder.commit()
    assert len(repo) == 0


def test_reference_to_a_real_experiment_is_fine():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    builder = repo.new(branch="side", structure=_cake(), title="v2", intent="x")
    builder.add_reference(role="benchmark", label="v1 for comparison", experiment_id=v1.id)
    committed = builder.commit()
    assert committed.references[0].experiment_id == v1.id


def test_moving_a_branch_backwards_is_rejected_like_committing_over_its_tip():
    # Regression: _commit refuses at length to move a branch onto a commit that would strand its
    # tip, and tag() demands force= to repoint - but branch() wrote the pointer with no guard at
    # all, so the same history could be abandoned through the neighbouring public method.
    repo = Repository()
    a1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    a2 = repo.derive(a1.id, title="v2", intent="x").commit()

    with pytest.raises(FollowError, match="abandon"):
        repo.branch("main", a1.id)

    assert repo.branches["main"] == a2.id
    assert [e.id for e in repo.log("main")] == [a2.id, a1.id]


def test_moving_a_branch_sideways_onto_an_unrelated_line_is_rejected():
    repo = Repository()
    a1 = repo.new(branch="main", structure=_cake(), title="main-v1", intent="x").commit()
    other = repo.new(branch="other", structure=_cake(220), title="other-v1", intent="x").commit()

    with pytest.raises(FollowError, match="abandon"):
        repo.branch("main", other.id)
    assert repo.branches["main"] == a1.id


def test_creating_a_branch_and_fast_forwarding_it_need_no_force():
    repo = Repository()
    a1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    a2 = repo.derive(a1.id, title="v2", intent="x").commit()

    repo.branch("stable", a1.id)  # brand-new name: nothing to abandon
    assert repo.branches["stable"] == a1.id

    repo.branch("stable", a2.id)  # forward onto a descendant: nothing becomes unreachable
    assert repo.branches["stable"] == a2.id

    repo.branch("stable", a2.id)  # a no-op move is fine too
    assert repo.branches["stable"] == a2.id


def test_fast_forward_is_recognised_through_the_second_parent_of_a_merge():
    # a merge commit descends from BOTH its parents; reaching the tip only through the second
    # one is still real history, so moving the branch there loses nothing and must be allowed
    repo = Repository()
    a1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    side_builder = repo.derive(a1.id, new_branch="side", title="side", intent="x")
    side_builder.structure.ingredients["flour"] = Quantity(value=300, unit="g")
    side_tip = side_builder.commit()
    merged = repo.merge("main", side_tip.id, title="merge", intent="x").commit()

    repo.branch("side", merged.id)
    assert repo.branches["side"] == merged.id


def test_force_is_the_deliberate_escape_hatch_for_moving_a_branch():
    repo = Repository()
    a1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    a2 = repo.derive(a1.id, title="v2", intent="x").commit()

    repo.branch("main", a1.id, force=True)
    assert repo.branches["main"] == a1.id
    assert a2.id in repo  # still stored, just no longer on the branch
