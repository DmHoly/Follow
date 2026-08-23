from examples.recipe import BakeStep, CakeRecipe
from follow import Quantity, Repository, render_fiche, render_log


def _cake(flour_g: float) -> CakeRecipe:
    return CakeRecipe(
        name="Vanilla cake",
        ingredients={"flour": Quantity(value=flour_g, unit="g"), "sugar": Quantity(value=150, unit="g")},
        bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def _repo_with_history() -> tuple[Repository, str, str]:
    repo = Repository()
    baseline = (
        repo.new(branch="main", structure=_cake(200), title="Baseline", intent="Reference bake")
        .add_objective(name="rise", metric="height_cm", direction="maximize", target=5.0, tolerance=0.5)
        .add_step(name="Mix", description="Combine dry ingredients")
        .commit()
    )
    variant_builder = repo.derive(baseline.id, title="More flour", intent="Does more flour improve the rise?")
    variant_builder.structure.ingredients["flour"] = Quantity(value=240, unit="g")
    variant_builder.add_evidence(
        id="ev1", description="Oven log photo", source="file:///data/bake2/log.jpg", metrics={"height_cm": Quantity(value=5.4, unit="cm")}
    )
    variant_builder.conclude(summary="Rise improved slightly.", decision="promote")
    variant = variant_builder.commit()
    return repo, baseline.id, variant.id


def test_fiche_mentions_intent_structure_and_conclusion():
    repo, _, variant_id = _repo_with_history()
    fiche = render_fiche(repo.get(variant_id), repo)
    assert "Does more flour improve the rise?" in fiche
    assert "flour" in fiche
    assert "promote" in fiche
    assert "Oven log photo" in fiche


def test_fiche_surfaces_the_diff_against_the_baseline():
    repo, baseline_id, variant_id = _repo_with_history()
    fiche = render_fiche(repo.get(variant_id), repo)
    assert "Paramètres modifiés" in fiche
    assert "ingredients.flour" in fiche
    assert baseline_id in fiche


def test_fiche_shows_next_steps_and_the_evidence_backing_each_objective_result():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="Reference bake")
    builder.add_objective(name="rise", metric="height_cm", direction="maximize", target=5.0)
    builder.add_evidence(id="ev1", description="Oven log photo", source="file:///data/log.jpg")
    builder.conclude(
        summary="Rose as expected.",
        decision="promote",
        next_steps="Scale up to a full batch.",
        objective_results=[dict(objective="rise", status="met", observed=Quantity(value=5.2, unit="cm"), evidence_ids=["ev1"])],
    )
    exp = builder.commit()

    fiche = render_fiche(exp, repo)
    assert "Scale up to a full batch." in fiche
    assert "`ev1`" in fiche


def test_render_log_lists_history_oldest_last():
    repo, baseline_id, variant_id = _repo_with_history()
    log_text = render_log(repo, "main")
    lines = log_text.splitlines()
    assert lines[0].startswith(variant_id)
    assert lines[1].startswith(baseline_id)

