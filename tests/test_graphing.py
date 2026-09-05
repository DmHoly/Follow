import re

import pytest

from examples.recipe import BakeStep, CakeRecipe
from follow import FollowError, Quantity, Repository, build_graph_figure, render_graph_html
from follow.presentation.graphing import _depths


def _cake(flour_g: float) -> CakeRecipe:
    return CakeRecipe(
        name="Vanilla cake",
        ingredients={"flour": Quantity(value=flour_g, unit="g"), "sugar": Quantity(value=150, unit="g")},
        bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def _repo_with_a_fork() -> tuple[Repository, str, str, str]:
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    v2 = repo.derive(v1.id, title="v2", intent="tweak").commit()
    fork_builder = repo.derive(v1.id, new_branch="less-sugar", title="fork", intent="try less sugar")
    fork_builder.structure.ingredients["sugar"] = Quantity(value=100, unit="g")
    fork = fork_builder.commit()
    return repo, v1.id, v2.id, fork.id


def test_layout_puts_root_above_its_descendants():
    repo, v1_id, v2_id, fork_id = _repo_with_a_fork()
    fig = build_graph_figure(repo)
    node_trace = fig.data[1]
    positions = dict(zip(node_trace.text, zip(node_trace.x, node_trace.y)))
    assert positions["v1"][1] < positions["v2"][1]
    assert positions["v1"][1] < positions["fork"][1]


def test_figure_has_one_node_per_experiment_and_two_branch_labels():
    repo, *_ = _repo_with_a_fork()
    fig = build_graph_figure(repo)
    node_trace = fig.data[1]
    branch_trace = fig.data[2]
    assert len(node_trace.x) == 3
    assert set(branch_trace.text) == {"⌥ main", "⌥ less-sugar"}


def test_a_custom_dag_draws_only_the_nodes_it_names():
    # a caller collapsing out some domain-specific notion of an "insignificant" commit (v2 here)
    # passes its own {id: [parent_ids]} instead of the full repo.graph()
    repo, v1_id, v2_id, fork_id = _repo_with_a_fork()
    collapsed = {v1_id: [], fork_id: [v1_id]}  # v2 dropped, fork reattached straight to v1

    fig = build_graph_figure(repo, dag=collapsed)
    node_trace = fig.data[1]
    assert set(node_trace.text) == {"v1", "fork"}


def test_a_custom_dag_defaults_to_the_full_repo_graph_when_omitted():
    repo, *_ = _repo_with_a_fork()
    assert build_graph_figure(repo).data[1].x == build_graph_figure(repo, dag=None).data[1].x


def test_render_graph_html_embeds_plotly_by_default(tmp_path):
    repo, v1_id, _, _ = _repo_with_a_fork()
    out = render_graph_html(repo, tmp_path / "graph.html")
    content = out.read_text(encoding="utf-8")

    # `assert out.exists()` used to sit here, after read_text() had already proved it.
    # The bundled plotly.js mentions its own CDN URL in its source, so what distinguishes the two
    # modes is whether the page *loads* from there - i.e. a <script src=...> pointing at it.
    assert not re.search(r'<script[^>]+src="https://cdn\.plot\.ly', content)
    assert out.stat().st_size > 1_000_000  # the library itself is in the file
    assert v1_id in content


def test_render_graph_html_can_point_at_the_cdn_instead(tmp_path):
    # the embed=False branch had no test at all, though it is what keeps a report light
    repo, v1_id, _, _ = _repo_with_a_fork()
    out = render_graph_html(repo, tmp_path / "graph.html", embed=False)
    content = out.read_text(encoding="utf-8")

    assert re.search(r'<script[^>]+src="https://cdn\.plot\.ly', content)
    assert v1_id in content
    assert out.stat().st_size < 200_000  # the embedded build is several megabytes


# -- _depths: iterative, order-independent, and loud about a corrupt lineage --------------------


def test_depths_are_correct_for_forks_and_merges():
    #      a          depth 0
    #     / \
    #    b   c        depth 1
    #     \ /
    #      d          depth 2 (merge: longest path from a root)
    dag = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}
    assert _depths(dag) == {"a": 0, "b": 1, "c": 1, "d": 2}


def test_depths_do_not_depend_on_the_iteration_order_of_the_dag():
    # the order a repository's objects come back in is whatever objects_dir.glob() gives, so the
    # result must not depend on it
    forward = {f"e{i}": ([f"e{i - 1}"] if i else []) for i in range(50)}
    backward = dict(reversed(list(forward.items())))
    assert _depths(backward) == _depths(forward)


def test_a_deep_lineage_does_not_blow_the_stack_in_either_order():
    # Regression: _depths recursed once per generation and memoised as it went, so an unlucky
    # dict order (root last) recursed all the way down and raised RecursionError - on the very
    # same repository that rendered fine when the order happened to be favourable.
    depth = 5000
    forward = {f"e{i}": ([f"e{i - 1}"] if i else []) for i in range(depth)}
    backward = dict(reversed(list(forward.items())))
    assert max(_depths(forward).values()) == depth - 1
    assert max(_depths(backward).values()) == depth - 1


def test_a_parent_outside_the_dag_is_ignored_not_counted_as_a_generation():
    # a partial graph (an experiment whose parent was not loaded) still lays out
    assert _depths({"child": ["missing"]}) == {"child": 0}


def test_a_lineage_cycle_raises_instead_of_silently_reporting_wrong_depths():
    # the old cycle "guard" wrote a provisional 0 and moved on, producing a plausible-looking
    # graph built on depths that were simply wrong
    with pytest.raises(FollowError, match="cycle"):
        _depths({"a": ["b"], "b": ["a"]})


def test_the_cycle_error_names_the_experiments_involved():
    with pytest.raises(FollowError, match="exp_a"):
        _depths({"exp_a": ["exp_b"], "exp_b": ["exp_a"], "clean": []})


def test_render_study_html_does_not_swallow_a_corrupt_lineage(monkeypatch):
    # render_study_html catches rendering failures so one bad figure doesn't cost the whole
    # report - but a corrupt repository is exactly what the reader must not be left unaware of
    from follow import render_study_html
    import follow.presentation.report as report

    repo, *_ = _repo_with_a_fork()

    def boom(_repo):
        raise FollowError("lineage cycle in the experiment graph, involving ['exp_x']")

    monkeypatch.setattr(report, "build_graph_figure", boom)
    with pytest.raises(FollowError, match="cycle"):
        render_study_html(repo, embed_plotly=False)


def test_render_study_html_still_survives_a_plain_rendering_failure(monkeypatch):
    from follow import render_study_html
    import follow.presentation.report as report

    repo, *_ = _repo_with_a_fork()

    def boom(_repo):
        raise RuntimeError("plotly exploded")

    monkeypatch.setattr(report, "build_graph_figure", boom)
    html = render_study_html(repo, embed_plotly=False)
    assert "follow graph" not in html  # the figure section is dropped...
    assert "Baseline" in html or "v1" in html  # ...and the rest of the report is still produced
