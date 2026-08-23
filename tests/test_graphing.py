from examples.recipe import BakeStep, CakeRecipe
from follow import Quantity, Repository, build_graph_figure, render_graph_html


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


def test_render_graph_html_writes_a_self_contained_file(tmp_path):
    repo, v1_id, v2_id, fork_id = _repo_with_a_fork()
    out = render_graph_html(repo, tmp_path / "graph.html")
    content = out.read_text()
    assert out.exists()
    assert "plotly" in content.lower()
    assert v1_id in content
