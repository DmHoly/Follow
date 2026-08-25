from conftest import assert_well_formed_html
from follow import analyze_batch
from follow.doe.design import check_identifiability

from demos.chocolate_cake_optimization import build_repository, render


def test_repository_shape():
    repo = build_repository()
    assert len(repo) == 10
    assert set(repo.branches) == {
        "main", "essai-temperature", "essai-sucre-beurre-naif", "essai-sucre-beurre",
        "essai-fractionnaire", "essai-screening-lhs", "candidat-sucre-beurre",
    }
    assert set(repo.tags) == {"recette-optimale"}


def test_baseline_declares_intent_structure_reference_and_objectives():
    repo = build_repository()
    baseline = repo.log("essai-temperature")[-1]
    assert baseline.intent
    assert baseline.hypothesis
    assert [r.role for r in baseline.references] == ["prior_art"]
    assert {o.name for o in baseline.objectives} == {"Hauteur", "Densite", "Intensite chocolat"}
    assert baseline.conclusion.next_steps  # ends in a next step, not a final verdict


def test_manual_sweep_varies_only_temperature():
    repo = build_repository()
    batch = repo.get("essai-temperature")
    structure = repo.load_structure(batch)
    assert len(structure.trials) == 5
    variation = analyze_batch(structure.trials, ignore=["trial_id"])
    assert [f.path for f in variation.varying] == ["bake_temperature"]


def test_naive_split_is_caught_by_check_identifiability_and_abandoned():
    repo = build_repository()
    naive = repo.get("essai-sucre-beurre-naif")
    assert naive.conclusion.status == "abandoned"
    assert naive.conclusion.decision == "abandon"

    structure = repo.load_structure(naive)
    flagged = check_identifiability(structure.trials, ["sugar", "butter"])
    assert len(flagged) == 1
    assert flagged[0][2] > 0.99  # near-perfect correlation - the mistake being illustrated


def test_full_factorial_fix_is_clean():
    repo = build_repository()
    batch = repo.get("essai-sucre-beurre")
    structure = repo.load_structure(batch)
    assert len(structure.trials) == 16  # 4 x 4
    assert check_identifiability(structure.trials, ["sugar", "butter"]) == []
    assert batch.conclusion.decision == "promote"


def test_fractional_factorial_is_resolution_iv():
    repo = build_repository()
    batch = repo.get("essai-fractionnaire")
    structure = repo.load_structure(batch)
    assert len(structure.trials) == 8  # 2^(4-1)
    assert "resolution 4" in batch.evidence[0].description


def test_latin_hypercube_screening_has_fifteen_trials():
    repo = build_repository()
    batch = repo.get("essai-screening-lhs")
    structure = repo.load_structure(batch)
    assert len(structure.trials) == 15


def test_merge_combines_temperature_with_sugar_and_butter():
    repo = build_repository()
    merged = [e for e in repo if e.title == "Fusion : temperature + sucre/beurre optimaux"][0]
    structure = repo.load_structure(merged)
    assert structure.bake_temperature.value == 190  # from main (ref_a), not overridden
    assert structure.sugar.value == 180  # taken from candidat-sucre-beurre (ref_b)
    assert structure.butter.value == 140
    assert len(merged.parents) == 2


def test_commit_form_is_required_from_the_final_validation_onward():
    repo = build_repository()
    assert repo.commit_form is not None
    final = repo.get("recette-optimale")
    assert final.form_answers == {"operateur": "Alice", "type_plan": "confirmation", "facteurs_croises_verifies": True}


def test_final_validation_batch_is_uniform():
    repo = build_repository()
    final = repo.get("recette-optimale")
    structure = repo.load_structure(final)
    assert len(structure.trials) == 4
    variation = analyze_batch(structure.trials, ignore=["trial_id"])
    assert variation.is_uniform is True


def test_render_produces_well_formed_html_covering_every_stage():
    repo = build_repository()
    html = render(repo, embed_plotly=False)
    assert_well_formed_html(html)
    assert html.startswith("<title>")
    for marker in ["Recette de reference", "Split manuel", "Split naif", "factoriel complet", "fractionnaire", "Latin Hypercube", "Fusion :", "recette-optimale"]:
        assert marker in html
