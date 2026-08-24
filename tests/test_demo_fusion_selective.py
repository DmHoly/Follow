from demos.fusion_selective import build_repository, render


def test_repository_shape():
    repo = build_repository()
    assert len(repo) == 6
    assert set(repo.branches) == {"main", "essai-cuisson"}


def test_merge_took_only_the_baking_step_from_the_branch():
    repo = build_repository()
    merged = repo.get("main")
    assert len(merged.parents) == 2
    assert merged.steps[2].parameters["temperature"].value == 175
    assert merged.steps[0].name == "Melanger le sec"


def test_render_produces_a_well_formed_page():
    repo = build_repository()
    html = render(repo, embed_plotly=False)
    assert html.count("<div") == html.count("</div>")
    assert "<title>Fusion sélective</title>" in html
    assert merged_id(repo) in html


def merged_id(repo) -> str:
    return repo.get("main").id
