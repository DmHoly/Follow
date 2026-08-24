"""Direct tests of the new ergonomic fiche building blocks (follow/report.py): objectives_table,
results_table, experiment_fiche, and batch_table's standalone=False mode - as opposed to
tests/test_report.py, which exercises the fully automatic render_study_html.
"""

from examples.recipe import BakeStep, CakeRecipe
from follow import BatchFactor, BatchVariation, Quantity, Repository, render_study_html
from follow.report import batch_table, experiment_fiche, objectives_table, render_page, results_table


def _cake() -> CakeRecipe:
    return CakeRecipe(
        name="Vanilla cake",
        ingredients={"flour": Quantity(value=200, unit="g")},
        bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def test_objectives_table_empty_is_blank():
    assert objectives_table([]) == ""


def test_objectives_table_renders_target_tolerance_range_and_rationale():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_objective(name="Rise", metric="height_cm", direction="maximize", target=5.0, tolerance=0.5, rationale="Taller is better")
    builder.add_objective(name="Coverage", metric="pct", direction="range", range=(0.4, 0.6))
    exp = builder.commit()

    html = objectives_table(exp.objectives)
    assert "Objectifs de l'étude" in html
    assert "Rise" in html and "cible 5.0" in html and "± 0.5" in html and "Taller is better" in html
    assert "Coverage" in html and "plage 0.4" in html and "0.6" in html


def test_objectives_table_escapes_untrusted_text():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_objective(name="<script>alert(1)</script>", metric="m", direction="observe")
    exp = builder.commit()

    html = objectives_table(exp.objectives)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_results_table_links_verdict_to_its_cited_evidence():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_objective(name="Rise", metric="height_cm", direction="maximize", target=5.0)
    builder.add_evidence(id="ev1", description="Notebook d'analyse", source="notebook:///a.ipynb")
    builder.conclude(
        status="concluded",
        objective_results=[dict(objective="Rise", status="met", observed=Quantity(value=5.5, unit="cm"), reasoning="Above target", evidence_ids=["ev1"])],
    )
    exp = builder.commit()

    html = results_table(exp.conclusion.objective_results, exp.evidence)
    assert "Résultats" in html
    assert 'class="result-verdict met"' in html
    assert "5.5 cm" in html
    assert "Above target" in html
    assert '<a class="evidence-link" href="notebook:///a.ipynb">Notebook d&#x27;analyse</a>' in html
    assert "Autres preuves" not in html  # the one piece of evidence IS cited


def test_results_table_surfaces_evidence_not_cited_by_any_result():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_evidence(id="ev-orphan", description="Raw measurements", source="file:///data.csv", metrics={"yield": Quantity(value=91, unit="%")})
    exp = builder.commit()

    html = results_table(exp.conclusion.objective_results, exp.evidence)
    assert "Autres preuves" in html
    assert "Raw measurements" in html
    assert "91 %" in html


def test_results_table_empty_when_nothing_to_show():
    assert results_table([], []) == ""


def test_results_table_handles_a_dangling_evidence_id_gracefully():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_objective(name="Rise", metric="height_cm", direction="maximize")
    builder.conclude(
        status="concluded",
        objective_results=[dict(objective="Rise", status="inconclusive", evidence_ids=["does-not-exist"])],
    )
    exp = builder.commit()

    html = results_table(exp.conclusion.objective_results, exp.evidence)
    assert "does-not-exist" in html  # shown as plain text, not silently dropped
    assert 'class="result-verdict inconclusive"' in html


def test_batch_table_standalone_false_is_a_fiche_row_not_a_card():
    variation = BatchVariation(entity_count=2, constant={}, varying=[BatchFactor(path="x", values=[1, 2])])
    standalone = batch_table(variation, title="Split")
    embedded = batch_table(variation, title="Split", standalone=False)
    assert '<div class="fiche-card">' in standalone
    assert '<div class="fiche-card">' not in embedded
    assert '<div class="fiche-row">' in embedded
    assert "Split" in embedded


def test_experiment_fiche_full_composition_reads_top_to_bottom():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="Baseline", intent="Establish a reference", hypothesis="More flour rises less")
    builder.add_objective(name="Rise", metric="height_cm", direction="maximize", target=5.0)
    builder.add_evidence(id="ev1", description="Probe measurement", source="file:///probe.csv")
    builder.conclude(
        status="concluded", decision="promote",
        summary="Rose as expected.",
        next_steps="Scale up to a full batch.",
        objective_results=[dict(objective="Rise", status="met", observed=Quantity(value=5.2, unit="cm"), evidence_ids=["ev1"])],
    )
    exp = builder.commit()

    html = experiment_fiche(exp, split='<div class="fiche-row"><div class="fiche-label">Split</div></div>')

    order = [html.index(marker) for marker in ("Establish a reference", "More flour rises less", "Objectifs de l'étude", "Split", "Résultats", "Rose as expected.", "Scale up to a full batch.")]
    assert order == sorted(order)  # every section appears in the documented reading order
    assert "promote" in html
    assert "concluded" in html


def test_experiment_fiche_omits_optional_sections_cleanly():
    repo = Repository()
    exp = repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()

    html = experiment_fiche(exp)
    assert "Hypothèse" not in html
    assert "Objectifs de l'étude" not in html
    assert "Résultats" not in html
    assert "Suite" not in html
    assert '<div class="fiche-card">' in html


def test_experiment_fiche_escapes_untrusted_intent_and_summary():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="<img src=x onerror=alert(1)>")
    builder.conclude(status="concluded", summary="<b>bold</b> & unescaped")
    exp = builder.commit()

    html = experiment_fiche(exp)
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img" in html
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; unescaped" in html


def test_experiment_fiche_renders_parent_pills_when_given():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(), title="Baseline", intent="x").commit()
    builder = repo.derive(v1.id, title="v2", intent="y")
    exp = builder.commit()

    html = experiment_fiche(exp, parents=[("parent", "main", f"{v1.id[:12]} — Baseline")])
    assert "parent-pill" in html
    assert v1.id[:12] in html


# -- render_page: what is escaped, and what stays raw by contract ------------------------------


def test_render_page_escapes_the_title_and_meta_description():
    # both land in slots where markup is never meaningful (<title> text, a content="..."
    # attribute), so an unescaped value there can only break out of its context
    html = render_page(
        title='X"><script>alert(1)</script>',
        description='" onload="evil()',
        eyebrow="e", heading="h", subtitle="s", stat_chips=[], sections=[], footer="",
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert 'content="" onload="evil()"' not in html


def test_render_page_keeps_composed_html_in_the_heading_and_subtitle():
    # the documented contract the demos rely on: these slots take HTML the caller composed
    html = render_page(
        title="t", description="d", eyebrow="Follow · démo",
        heading="Une <b>fusion</b> sélective",
        subtitle="voir <code>main</code>",
        stat_chips=["<b>6</b> commits"], sections=[], footer="",
    )
    assert "<b>fusion</b>" in html
    assert "<code>main</code>" in html
    assert "<b>6</b> commits" in html


def test_render_study_html_escapes_a_caller_supplied_title():
    repo = Repository()
    repo.new(branch="main", structure=_cake(), title="v1", intent="x").commit()
    html = render_study_html(repo, title="<script>alert(1)</script>", embed_plotly=False)
    assert "<script>alert(1)</script>" not in html


def test_a_javascript_uri_evidence_source_is_not_turned_into_a_link():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_objective(name="Rise", metric="m")
    builder.add_evidence(id="ev1", description="fausse preuve", source="javascript:alert(document.domain)")
    builder.conclude(objective_results=[dict(objective="Rise", status="met", evidence_ids=["ev1"])])
    exp = builder.commit()

    html = results_table(exp.conclusion.objective_results, exp.evidence)
    assert "javascript:" not in html
    assert "fausse preuve" in html  # still shown, just not clickable


def test_a_javascript_uri_is_caught_even_when_split_by_control_characters():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_evidence(id="ev1", description="preuve", source="java\tscript:alert(1)")
    exp = builder.commit()

    html = results_table([], exp.evidence)
    assert "<a" not in html
    assert "preuve" in html


def test_ordinary_evidence_sources_are_still_links():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.add_evidence(id="ev1", description="notebook", source="notebook:///analyse.ipynb")
    builder.add_evidence(id="ev2", description="photo", source="file:///data/log.jpg")
    builder.add_evidence(id="ev3", description="article", source="https://example.org/a")
    exp = builder.commit()

    html = results_table([], exp.evidence)
    assert 'href="notebook:///analyse.ipynb"' in html
    assert 'href="file:///data/log.jpg"' in html
    assert 'href="https://example.org/a"' in html
