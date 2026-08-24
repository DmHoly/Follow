from conftest import assert_well_formed_html
from examples.recipe import BakeStep, CakeRecipe
from follow import Quantity, Repository, render_study_html


def _cake(flour_g: float) -> CakeRecipe:
    return CakeRecipe(
        name="Vanilla cake",
        ingredients={"flour": Quantity(value=flour_g, unit="g")},
        bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def test_root_experiment_has_no_lineage_section():
    repo = Repository()
    repo.new(branch="main", structure=_cake(200), title="Baseline", intent="start").commit()
    html = render_study_html(repo)
    assert "Changements depuis le parent" not in html
    assert "Résolution de la fusion" not in html


def test_single_parent_shows_a_diff_not_a_full_dump():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="start").commit()
    variant = repo.derive(v1.id, title="More flour", intent="more flour")
    variant.structure.ingredients["flour"] = Quantity(value=240, unit="g")
    variant.commit()

    html = render_study_html(repo)
    assert "Changements depuis le parent" in html
    assert "ingredients.flour" in html
    assert "200 g" in html and "240 g" in html


def test_merge_attribution_matches_which_parent_a_value_came_from():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="start").commit()
    branch = repo.derive(v1.id, new_branch="feature", title="Feature", intent="try something")
    branch.structure.ingredients["flour"] = Quantity(value=300, unit="g")
    feature_tip = branch.commit()

    merged = repo.merge(
        "main", feature_tip.id, title="Merge", intent="merge", take_structure=["ingredients.flour"]
    ).commit()

    html = render_study_html(repo)
    assert "Résolution de la fusion (main + feature)" in html
    assert "valeur reprise du second parent" in html
    assert "300 g" in html
    assert repo.get(merged.id).id in html


def test_merge_attribution_reports_kept_side_too():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="start").commit()
    branch = repo.derive(v1.id, new_branch="feature", title="Feature", intent="try something")
    branch.structure.ingredients["flour"] = Quantity(value=300, unit="g")
    feature_tip = branch.commit()

    # take_structure is empty: the merge deliberately keeps main's value everywhere
    repo.merge("main", feature_tip.id, title="Merge", intent="merge").commit()

    html = render_study_html(repo)
    assert "valeur conservée du premier parent" in html
    assert "valeur reprise du second parent" not in html


def test_untrusted_text_is_html_escaped():
    repo = Repository()
    repo.new(
        branch="main",
        structure=_cake(200),
        title='<script>alert(1)</script>',
        intent="Contains <b>markup</b> & an ampersand",
    ).commit()

    html = render_study_html(repo)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html


def test_ref_filters_to_one_lineage():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="start").commit()
    repo.derive(v1.id, new_branch="side", title="Side branch", intent="explore").commit()
    repo.derive(v1.id, title="Main continues", intent="continue").commit()

    html = render_study_html(repo, ref="side")
    assert '<div class="fiche-title">Side branch</div>' in html
    # "Main continues" is still a legitimate label in the (always-full) filiation graph;
    # what `ref` filters is which experiments get their own report section.
    assert '<div class="fiche-title">Main continues</div>' not in html


def test_output_is_well_formed_html():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="start").commit()
    branch = repo.derive(v1.id, new_branch="feature", title="Feature", intent="try something")
    branch.structure.ingredients["flour"] = Quantity(value=300, unit="g")
    feature_tip = branch.commit()
    repo.merge("main", feature_tip.id, title="Merge", intent="merge", take_structure=["ingredients.flour"]).commit()

    html = render_study_html(repo, embed_plotly=False)
    assert_well_formed_html(html)
    assert html.startswith("<title>")
