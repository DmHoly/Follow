"""Deliberate misuse of the core engine: each test tries to do something a user could plausibly
attempt by mistake, and checks it now fails loudly and clearly instead of silently corrupting
state or crashing with a confusing low-level error. Every one of these was reproduced as a real,
silent problem before the corresponding fix.
"""

import json

import pytest
from pydantic import ValidationError

from examples.mosfet import Layer, MOSFETStructure
from examples.recipe import BakeStep, CakeRecipe
from follow import (
    BatchShapeError,
    DanglingRefError,
    ExperimentNotFoundError,
    FollowError,
    NothingToCommitError,
    PathNotFoundError,
    Quantity,
    ReferenceLink,
    Repository,
    Structure,
    analyze_batch,
    format_value,
)
from follow.commit_form import CommitForm
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


# -- a repository whose refs no longer match its objects ---------------------------------------


def _repo_with_a_deleted_object(tmp_path):
    """A persisted repository whose object files were removed behind its back - the state an
    interrupted write, a partial copy or a stray `rm` leaves behind."""
    repo = Repository(tmp_path)
    committed = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    for object_file in (tmp_path / "objects").glob("*.json"):
        object_file.unlink()
    return Repository(tmp_path), committed.id


def test_a_branch_pointing_at_a_missing_object_raises_a_named_error_not_a_bare_keyerror(tmp_path):
    # Regression: _resolve_ref returned whatever id refs.json named without checking it was
    # stored, so get() failed on a bare KeyError carrying nothing but a hash.
    repo, missing_id = _repo_with_a_deleted_object(tmp_path)

    with pytest.raises(DanglingRefError) as excinfo:
        repo.get("main")
    message = str(excinfo.value)
    assert "main" in message and missing_id in message
    assert "refs are out of step" in message


def test_contains_agrees_with_get_on_a_dangling_ref(tmp_path):
    # `"main" in repo` used to answer True for a ref get() could not honour
    repo, _ = _repo_with_a_deleted_object(tmp_path)
    assert "main" not in repo


def test_a_dangling_ref_is_still_an_experiment_not_found_error(tmp_path):
    # callers already guarding for "this ref doesn't resolve" must keep working
    repo, _ = _repo_with_a_deleted_object(tmp_path)
    with pytest.raises(ExperimentNotFoundError):
        repo.get("main")


def test_an_unknown_name_stays_distinct_from_a_broken_one(tmp_path):
    # the two call for completely different fixes, so they must not report the same thing
    repo, _ = _repo_with_a_deleted_object(tmp_path)
    with pytest.raises(ExperimentNotFoundError) as excinfo:
        repo.get("never-existed")
    assert not isinstance(excinfo.value, DanglingRefError)
    assert "No experiment, branch or tag matches" in str(excinfo.value)


def test_log_reports_a_missing_parent_instead_of_a_bare_keyerror(tmp_path):
    repo = Repository(tmp_path)
    v1 = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    repo.derive(v1.id, title="v2", intent="x").commit()
    (tmp_path / "objects" / f"{v1.id}.json").unlink()  # the root goes missing, the tip stays

    reloaded = Repository(tmp_path)
    with pytest.raises(DanglingRefError, match=v1.id):
        reloaded.log("main")


def test_committing_onto_a_branch_whose_tip_went_missing_is_reported_clearly(tmp_path):
    repo, missing_id = _repo_with_a_deleted_object(tmp_path)
    builder = repo.new(branch="main", structure=_cake(220), title="v2", intent="x", parents=[])
    with pytest.raises(DanglingRefError, match=missing_id):
        builder.commit()


# -- durability of the repository's own writes -------------------------------------------------


def test_an_interrupted_write_leaves_the_previous_refs_file_intact(tmp_path, monkeypatch):
    # Regression: refs.json was written with a plain write_text, which truncates first and fills
    # second - an interruption in between left a half file, i.e. a repository whose branches no
    # longer name real objects.
    import follow.repository as repository_module

    repo = Repository(tmp_path)
    repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    before = (tmp_path / "refs.json").read_text(encoding="utf-8")

    def interrupted(_src, _dst):
        raise KeyboardInterrupt("power cut")

    monkeypatch.setattr(repository_module.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        repo.new(branch="side", structure=_cake(220), title="v2", intent="x").commit()
    monkeypatch.undo()

    assert (tmp_path / "refs.json").read_text(encoding="utf-8") == before
    assert json.loads(before)["branches"]["main"]  # still parseable, still meaningful
    assert not list(tmp_path.rglob(".*.tmp"))  # no stray temporary left behind
    assert len(Repository(tmp_path)) == 1  # and the repository still reloads


def test_accented_text_round_trips_through_the_stored_files(tmp_path):
    # the draft writer uses ensure_ascii=False, so the encoding has to be pinned rather than
    # left to the platform default
    repo = Repository(tmp_path)
    committed = repo.new(
        branch="main", structure=_cake(), title="Cuisson à 180 °C", intent="Réduire l'écart"
    ).commit()

    raw = (tmp_path / "objects" / f"{committed.id}.json").read_text(encoding="utf-8")
    assert "180 °C" in raw
    assert Repository(tmp_path).get("main").title == "Cuisson à 180 °C"


def test_a_write_torn_in_half_never_reaches_the_real_refs_file(tmp_path, monkeypatch):
    # The failure the atomic write actually exists for: the process dies *during* the write, with
    # half the bytes already on disk. With a plain write_text (truncate, then fill) that left a
    # refs.json that no longer parsed at all - the repository would not even reload.
    import builtins

    repo = Repository(tmp_path)
    repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    before = (tmp_path / "refs.json").read_text(encoding="utf-8")

    real_open = builtins.open

    class _Torn:
        """A file handle that writes half of what it is given, then the power goes out."""

        def __init__(self, handle):
            self._handle = handle

        def write(self, text):
            self._handle.write(text[: len(text) // 2])
            raise KeyboardInterrupt("power cut mid-write")

        def __getattr__(self, name):
            return getattr(self._handle, name)

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            self._handle.close()
            return False

    def opener(path, mode="r", *args, **kwargs):
        handle = real_open(path, mode, *args, **kwargs)
        # covers both the target and the ".refs.json.<pid>.tmp" the atomic write goes through
        return _Torn(handle) if "w" in mode and "refs.json" in str(path) else handle

    monkeypatch.setattr(builtins, "open", opener)
    with pytest.raises(KeyboardInterrupt):
        repo.new(branch="side", structure=_cake(220), title="v2", intent="x").commit()
    monkeypatch.undo()

    after = (tmp_path / "refs.json").read_text(encoding="utf-8")
    assert after == before
    assert json.loads(after)["branches"]["main"]  # parses, and still names the old tip

    # The object file for the abandoned commit was written before the refs, so it survives on
    # disk - an unreferenced object, exactly what git leaves behind for gc, and harmless: no
    # branch names it. What must never happen is the mirror image, a ref naming a missing
    # object, which is what a torn refs.json produced.
    reloaded = Repository(tmp_path)
    assert reloaded.get("main").title == "v1"
    assert set(reloaded.branches) == {"main"}
    for name in reloaded.branches:
        assert name in reloaded  # every ref still resolves


# -- protocol steps are matched on their number, not their slot ---------------------------------


def _protocol_repo():
    """main: Mélanger(1), Reposer(2), Cuire(3) - side drops the resting step and bakes hotter,
    without renumbering what remains."""
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_step(order=1, name="Mélanger")
    builder.add_step(order=2, name="Reposer")
    builder.add_step(order=3, name="Cuire", parameters={"temperature": Quantity(value=180, unit="C")})
    v1 = builder.commit()

    side = repo.derive(v1.id, new_branch="side", title="v2", intent="drop the rest, bake hotter")
    side.steps = [s for s in side.steps if s.name != "Reposer"]
    side.steps[-1] = side.steps[-1].model_copy(update={"parameters": {"temperature": Quantity(value=200, unit="C")}})
    return repo, v1, side.commit()


def test_removing_a_step_reads_as_one_removal_not_a_cascade_of_changes():
    # Regression: steps were compared position by position, so dropping a step in the middle
    # shifted every later one - the diff claimed "Reposer" had become "Cuire" and that "Cuire"
    # had been deleted, when only one step was removed and one parameter changed.
    repo, _, tip = _protocol_repo()
    entries = {e.path: e.kind for e in repo.diff_steps("main", tip.id)}

    assert entries == {"2": "removed", "3.parameters.temperature": "changed"}


def test_a_take_steps_path_names_the_step_number_not_the_list_slot():
    repo, _, tip = _protocol_repo()
    merged = repo.merge(
        "main", tip.id, title="merge", intent="take just the temperature",
        take_steps=["3.parameters.temperature"],
    ).commit()

    by_order = {s.order: s for s in merged.steps}
    assert set(by_order) == {1, 2, 3}  # main's resting step is kept: it was not listed
    assert by_order[3].parameters["temperature"].value == 200  # taken from the branch
    assert by_order[2].name == "Reposer"


def test_taking_a_whole_step_by_its_number():
    repo, _, tip = _protocol_repo()
    merged = repo.merge("main", tip.id, title="merge", intent="x", take_steps=["3"]).commit()
    assert {s.order for s in merged.steps} == {1, 2, 3}
    assert merged.steps[-1].parameters["temperature"].value == 200


def test_a_step_number_absent_from_the_branch_is_reported_not_silently_misread():
    repo, _, tip = _protocol_repo()
    with pytest.raises(PathNotFoundError, match="'2'"):
        repo.merge("main", tip.id, title="merge", intent="x", take_steps=["2"])


def test_merged_steps_come_back_in_protocol_order():
    repo, v1, tip = _protocol_repo()
    merged = repo.merge("main", tip.id, title="merge", intent="x", take_steps=["3"]).commit()
    assert [s.order for s in merged.steps] == sorted(s.order for s in merged.steps)


def test_step_diff_is_listed_in_protocol_order_not_lexicographic_order():
    # keys are the order as a string, so a plain sort would read 1, 10, 11, 2
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    for order in range(1, 12):
        builder.add_step(order=order, name=f"étape {order}")
    v1 = builder.commit()

    side = repo.derive(v1.id, new_branch="side", title="v2", intent="rename them all")
    side.steps = [s.model_copy(update={"name": f"{s.name} bis"}) for s in side.steps]
    tip = side.commit()

    orders = [int(e.path.split(".")[0]) for e in repo.diff_steps("main", tip.id)]
    assert orders == sorted(orders)
    assert orders[:3] == [1, 2, 3]


# -- the error hierarchy ------------------------------------------------------------------------


def test_every_error_follow_raises_is_a_follow_error():
    # Regression: FollowError was documented as the base class, but merge raised ValueError,
    # Structure.resolve KeyError, split_path ValueError, the commit form ValueError... so
    # `except FollowError` around a commit missed the most expected failure of all.
    import follow

    raisers = [
        lambda: Repository().get("nope"),
        lambda: Structure.resolve("never.Registered"),
        lambda: split_path("steps[abc]"),
        lambda: follow.analyze_batch([{"x": 1}, {"x": 1, "extra": 2}]),
        lambda: follow.sweep(_cake(), "not_a_field", [1, 2]),
        lambda: CommitForm.model_validate({"title": "t", "fields": [{"name": "a", "label": "A"}]}).validate_answers({}),
    ]
    for raiser in raisers:
        with pytest.raises(FollowError):
            raiser()


def test_the_builtin_each_error_used_to_be_still_catches_it():
    # callers written against the old behaviour must keep working
    with pytest.raises(KeyError):
        Structure.resolve("never.Registered")
    with pytest.raises(ValueError):
        split_path("steps[abc]")
    with pytest.raises(ValueError):
        CommitForm.model_validate({"title": "t", "fields": [{"name": "a", "label": "A"}]}).validate_answers({})


# -- content addressing, step numbering, batch shape, one Quantity renderer ---------------------


def test_identical_content_yields_the_same_id_in_a_fresh_repository():
    # Regression: created_at was part of the hashed payload, so content_id's promise that
    # identical payloads dedupe was false - the id depended on the clock, not on the content.
    first = Repository().new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    second = Repository().new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    assert first.id == second.id


def test_a_different_branch_or_parent_still_yields_a_different_id():
    repo = Repository()
    a = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    b = repo.new(branch="side", structure=_cake(), title="v1", intent="x").commit()
    assert a.id != b.id  # branch is part of the content


def test_add_step_numbers_after_the_highest_order_not_the_count():
    # Regression: the auto order was len(steps) + 1, which collided with any hand-set order -
    # and nothing said so until commit ran the validator.
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_step(name="A", order=2)
    builder.add_step(name="B")

    assert [s.order for s in builder.steps] == [2, 3]
    builder.commit()  # no longer a late ValidationError


def test_a_field_present_only_on_a_later_entity_is_reported_not_dropped():
    # Regression: leaf paths were read off the first entity alone, so an extra field on entity
    # 2..N vanished from the analysis - a real DOE factor missing from the report.
    with pytest.raises(BatchShapeError, match="extra"):
        analyze_batch([{"x": 1}, {"x": 1, "extra": 999}])


def test_str_and_format_value_render_a_quantity_identically():
    # Regression: two separate implementations that had drifted - str() dropped `note`, so a
    # fiche showed it on structure values and silently lost it on step parameters.
    quantity = Quantity(value=200, unit="g", uncertainty=5, note="à froid")
    assert str(quantity) == format_value(quantity.model_dump(mode="json"))
    assert "à froid" in str(quantity)
