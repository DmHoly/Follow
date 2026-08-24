from conftest import assert_well_formed_html
from demos.entity_tracking import build_repository, render


def test_repository_shape():
    repo = build_repository()
    assert len(repo) == 3
    assert set(repo.branches) == {"main", "moule-vert-nutella", "moule-rouge-glacage"}


def test_followups_have_no_git_relationship_to_the_split():
    repo = build_repository()
    split = repo.get("main")
    nutella = repo.get("moule-vert-nutella")
    glacage = repo.get("moule-rouge-glacage")

    assert nutella.parents == []
    assert glacage.parents == []
    assert not any(r.experiment_id == split.id for r in nutella.references)
    assert not any(r.experiment_id == split.id for r in glacage.references)


def test_find_entity_links_the_split_and_its_followup_by_name_alone():
    repo = build_repository()
    split = repo.get("main")
    nutella = repo.get("moule-vert-nutella")
    glacage = repo.get("moule-rouge-glacage")

    assert [e.id for e in repo.find_entity("moule-vert")] == [split.id, nutella.id]
    assert [e.id for e in repo.find_entity("moule-rouge")] == [split.id, glacage.id]
    assert repo.find_entity("moule-jaune") == []


def test_render_produces_a_well_formed_page():
    repo = build_repository()
    html = render(repo, embed_plotly=False)
    assert_well_formed_html(html)
    assert "<title>Suivre une entité physique</title>" in html
    assert "moule-vert" in html
