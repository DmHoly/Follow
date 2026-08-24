import pytest

from examples.recipe import BakeStep, CakeRecipe
from follow import ExperimentNotFoundError, Quantity, Repository


def _cake(flour_g: float) -> CakeRecipe:
    return CakeRecipe(
        name="Vanilla cake",
        ingredients={"flour": Quantity(value=flour_g, unit="g"), "sugar": Quantity(value=150, unit="g")},
        bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def test_commit_computes_a_stable_content_id():
    repo = Repository()
    baseline = (
        repo.new(branch="main", structure=_cake(200), title="Baseline vanilla cake", intent="Establish a reference bake")
        .add_objective(name="rise", metric="height_cm", direction="maximize", target=5.0)
        .commit()
    )
    assert baseline.id.startswith("exp_")
    assert baseline.parents == []
    assert repo.get("main").id == baseline.id


def test_derive_carries_over_config_and_adds_a_baseline_reference():
    repo = Repository()
    baseline = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="Reference bake").commit()

    variant = (
        repo.derive(baseline.id, title="More flour", intent="Does more flour improve the rise?")
    )
    variant.structure.ingredients["flour"] = Quantity(value=240, unit="g")
    committed = variant.commit()

    assert committed.parents == [baseline.id]
    assert any(r.role == "baseline" and r.experiment_id == baseline.id for r in committed.references)
    assert committed.objectives == baseline.objectives


def test_diff_between_baseline_and_derived_experiment():
    repo = Repository()
    baseline = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="Reference bake").commit()

    variant_builder = repo.derive(baseline.id, title="More flour", intent="More flour")
    variant_builder.structure.ingredients["flour"] = Quantity(value=240, unit="g")
    variant = variant_builder.commit()

    diff = repo.diff(baseline.id, variant.id)
    assert diff.changed_paths == ["ingredients.flour"]


def test_log_walks_first_parent_history_newest_first():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    v2 = repo.derive(v1.id, title="v2", intent="tweak").commit()
    v3 = repo.derive(v2.id, title="v3", intent="tweak again").commit()

    history_ids = [exp.id for exp in repo.log("main")]
    assert history_ids == [v3.id, v2.id, v1.id]


def test_branching_forks_without_disturbing_the_original_branch():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    experimental = repo.derive(v1.id, new_branch="less-sugar", title="Less sugar", intent="Try less sugar").commit()

    assert repo.branches["main"] == v1.id
    assert repo.branches["less-sugar"] == experimental.id


def test_tag_and_unknown_ref_lookup():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    repo.tag("champion", v1.id)

    assert repo.get("champion").id == v1.id
    with pytest.raises(ExperimentNotFoundError):
        repo.get("does-not-exist")


def test_persistence_round_trips_through_json_files(tmp_path):
    repo = Repository(tmp_path)
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    repo.derive(v1.id, title="v2", intent="tweak").commit()

    reloaded = Repository(tmp_path)
    assert len(reloaded) == 2
    assert reloaded.get("main").title == "v2"
    assert [e.id for e in reloaded.log("main")] == [e.id for e in repo.log("main")]


def test_contains_operator():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()

    assert v1.id in repo
    assert "main" in repo
    assert "does-not-exist" not in repo


def test_diff_from_baseline_on_the_builder_before_commit():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()

    root_builder = repo.new(branch="side", structure=_cake(200), title="root", intent="no baseline")
    assert root_builder.diff_from_baseline() is None

    variant = repo.derive(v1.id, title="v2", intent="more flour")
    variant.structure.ingredients["flour"] = Quantity(value=240, unit="g")
    diff = variant.diff_from_baseline()
    assert diff is not None
    assert diff.changed_paths == ["ingredients.flour"]


def test_branch_and_tag_persist_to_disk_when_called_directly(tmp_path):
    repo = Repository(tmp_path)
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    v2 = repo.derive(v1.id, title="v2", intent="tweak").commit()

    repo.branch("stable", v1.id)
    repo.tag("first-release", v1.id)

    reloaded = Repository(tmp_path)
    assert reloaded.branches["stable"] == v1.id
    assert reloaded.tags["first-release"] == v1.id
    assert reloaded.branches["main"] == v2.id


def test_tags_passed_at_commit_time_are_applied():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start", tags=["milestone"]).commit()

    assert repo.tags["milestone"] == v1.id
    assert repo.get("milestone").id == v1.id
