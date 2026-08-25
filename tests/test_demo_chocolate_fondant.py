from conftest import assert_well_formed_html
from demos.chocolate_fondant import SOURCES, build_repository, render


def test_ten_sources_are_cited():
    assert len(SOURCES) == 10
    assert all(s["url"].startswith("http") for s in SOURCES)


def test_repository_shape():
    repo = build_repository()
    assert len(repo) == 11
    assert set(repo.branches) == {"main", "essai-jaunes", "essai-repos", "essai-cuisson"}


def test_each_branch_isolates_its_own_variable():
    repo = build_repository()
    j2 = repo.get("essai-jaunes")
    assert repo.load_structure(j2).egg_yolks == 4
    assert j2.steps[5].parameters["temperature"].value == 200  # untouched by this branch

    r2 = repo.get("essai-repos")
    assert r2.steps[5].parameters["duree"].value == 15
    assert repo.load_structure(r2).egg_yolks == 0  # untouched by this branch

    c2 = repo.get("essai-cuisson")
    assert c2.steps[5].parameters["temperature"].value == 170
    assert repo.load_structure(c2).egg_yolks == 0  # untouched by this branch


def test_third_merge_is_flagged_inconclusive_before_validation():
    repo = build_repository()
    m3 = [e for e in repo if e.title == "Fusion : cuisson basse temperature"][0]
    assert m3.conclusion.decision == "inconclusive"
    # the unresolved tension this merge leaves behind: frozen-batter duration vs fresh-batter temp
    assert m3.steps[4].description.startswith("Congeler")
    assert m3.steps[5].parameters["temperature"].value == 170
    assert m3.steps[5].parameters["duree"].value == 10


def test_final_validation_resolves_the_gap_and_meets_the_objective():
    repo = build_repository()
    final = repo.get("recette-optimale")
    assert final.conclusion.decision == "promote"
    assert final.steps[5].parameters["temperature"].value == 170
    assert final.steps[5].parameters["duree"].value == 14  # adjusted, not just inherited from either parent
    assert final.conclusion.objective_results[0].status == "met"
    assert repo.load_structure(final).egg_yolks == 4  # merge 1's contribution still present


def test_render_produces_a_well_formed_page_citing_all_sources():
    repo = build_repository()
    html = render(repo, embed_plotly=False)
    assert_well_formed_html(html)
    assert "<title>Fondant optimal</title>" in html
    for source in SOURCES:
        assert source["url"] in html
