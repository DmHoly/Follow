from examples.recipe import BakeStep, CakeRecipe
from follow import Quantity, Repository


def _recipe() -> CakeRecipe:
    return CakeRecipe(
        name="Gateau",
        ingredients={"farine": Quantity(value=200, unit="g")},
        bake=BakeStep(temperature=Quantity(value=170, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def _five_steps(bake_temp: float, bake_duration: float) -> list[dict]:
    return [
        dict(order=1, name="Mélanger le sec"),
        dict(order=2, name="Mélanger le liquide"),
        dict(
            order=3,
            name="Cuire",
            parameters={
                "temperature": Quantity(value=bake_temp, unit="C"),
                "duree": Quantity(value=bake_duration, unit="min"),
            },
        ),
        dict(order=4, name="Refroidir"),
        dict(order=5, name="Glacer"),
    ]


def _repo_with_a_selective_merge() -> tuple[Repository, dict]:
    repo = Repository()

    v1 = repo.new(branch="main", structure=_recipe(), title="Baseline", intent="Etablir une reference")
    for step in _five_steps(170, 35):
        v1.add_step(**step)
    v1 = v1.commit()

    branch_a = repo.derive(v1.id, new_branch="essai-cuisson", title="Essai 160C", intent="Tester une cuisson plus douce")
    branch_a.steps[2] = branch_a.steps[2].model_copy(
        update={"parameters": {"temperature": Quantity(value=160, unit="C"), "duree": Quantity(value=40, unit="min")}}
    )
    branch_a.conclude(status="concluded", decision="branch", summary="Trop humide au centre.")
    a1 = branch_a.commit()

    branch_b = repo.derive(a1.id, title="Essai 185C", intent="Tester une cuisson plus vive")
    branch_b.steps[2] = branch_b.steps[2].model_copy(
        update={"parameters": {"temperature": Quantity(value=185, unit="C"), "duree": Quantity(value=30, unit="min")}}
    )
    branch_b.conclude(status="concluded", decision="branch", summary="Trop sec sur les bords.")
    a2 = branch_b.commit()

    branch_c = repo.derive(a2.id, title="Essai 175C", intent="Compromis entre les deux essais precedents")
    branch_c.steps[2] = branch_c.steps[2].model_copy(
        update={"parameters": {"temperature": Quantity(value=175, unit="C"), "duree": Quantity(value=32, unit="min")}}
    )
    branch_c.conclude(status="concluded", decision="promote", summary="Meilleure levee, mie moelleuse.")
    a3 = branch_c.commit()

    v2 = repo.derive(v1.id, title="Mélange plus long", intent="Un mélange plus long ameliore la texture")
    v2.steps[0] = v2.steps[0].model_copy(update={"name": "Mélanger le sec (4 min)"})
    v2.conclude(status="concluded", decision="promote", summary="Texture plus homogene.")
    v2 = v2.commit()

    merge_builder = repo.merge(
        v2.id,
        a3.id,
        title="Fusion: melange ameliore + cuisson optimisee",
        intent="Combiner le meilleur melange (main) et la temperature de cuisson optimisee (essai-cuisson)",
        take_steps=["[2]"],
    )
    merged = merge_builder.commit()

    return repo, {"v1": v1, "v2": v2, "a1": a1, "a2": a2, "a3": a3, "merged": merged}


def test_merge_commit_has_both_tips_as_parents():
    repo, exps = _repo_with_a_selective_merge()
    merged = exps["merged"]
    assert set(merged.parents) == {exps["v2"].id, exps["a3"].id}


def test_merge_took_only_step_three_from_the_test_branch():
    repo, exps = _repo_with_a_selective_merge()
    merged = exps["merged"]

    # step 3 (index 2) came from the winning test-branch experiment
    assert merged.steps[2].parameters["temperature"].value == 175
    assert merged.steps[2].parameters["duree"].value == 32

    # everything else - including main's own independent change - came from ref_a (main)
    assert merged.steps[0].name == "Mélanger le sec (4 min)"
    assert merged.steps[1].name == exps["v2"].steps[1].name
    assert merged.steps[3].name == exps["v2"].steps[3].name
    assert merged.steps[4].name == exps["v2"].steps[4].name


def test_merge_records_baseline_and_merge_source_references():
    repo, exps = _repo_with_a_selective_merge()
    merged = exps["merged"]
    roles = {r.role: r.experiment_id for r in merged.references}
    assert roles["baseline"] == exps["v2"].id
    assert roles["merge_source"] == exps["a3"].id


def test_main_branch_now_points_at_the_merge_commit():
    repo, exps = _repo_with_a_selective_merge()
    assert repo.branches["main"] == exps["merged"].id
    assert repo.branches["essai-cuisson"] == exps["a3"].id
