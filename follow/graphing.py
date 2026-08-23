from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import plotly.graph_objects as go

if TYPE_CHECKING:
    from .repository import Repository

_STATUS_COLORS = {
    "draft": "#9e9e9e",
    "running": "#1f77b4",
    "concluded": "#2ca02c",
    "abandoned": "#d62728",
}
_BRANCH_LABEL_COLOR = "#8a6d00"


def _depths(dag: dict[str, list[str]]) -> dict[str, int]:
    """Longest-path-from-a-root depth for each node, used as the layer/row of a layered layout."""
    depths: dict[str, int] = {}

    def depth(node: str) -> int:
        if node in depths:
            return depths[node]
        depths[node] = 0  # guard against cycles, which shouldn't exist but must not hang
        parents = [p for p in dag.get(node, []) if p in dag]
        depths[node] = 0 if not parents else 1 + max(depth(p) for p in parents)
        return depths[node]

    for node in dag:
        depth(node)
    return depths


def _layout(dag: dict[str, list[str]]) -> dict[str, tuple[float, float]]:
    """A minimal, dependency-free layered layout: one row per generation, nodes within a row
    ordered by the average x of their parents (a simple barycenter heuristic) to keep the
    lineage roughly untangled without needing a real graph-layout engine.
    """
    depths = _depths(dag)
    by_depth: dict[int, list[str]] = {}
    for node, d in depths.items():
        by_depth.setdefault(d, []).append(node)

    positions: dict[str, tuple[float, float]] = {}
    for d in sorted(by_depth):
        nodes = by_depth[d]
        if d == 0:
            nodes.sort()
        else:
            def barycenter(node: str, _d: int = d) -> float:
                xs = [positions[p][0] for p in dag.get(node, []) if p in positions]
                return sum(xs) / len(xs) if xs else 0.0

            nodes.sort(key=barycenter)
        offset = (len(nodes) - 1) / 2
        for i, node in enumerate(nodes):
            positions[node] = (i - offset, float(d))
    return positions


def build_graph_figure(repo: "Repository") -> go.Figure:
    """The full lineage graph as a Plotly figure: one marker per experiment, an edge per
    parent link, and a label at each branch tip - Follow's lightweight, dependency-light
    stand-in for a Graphviz rendering.
    """
    dag = repo.graph()
    positions = _layout(dag)
    experiments = {exp.id: exp for exp in repo}

    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for node, parents in dag.items():
        if node not in positions:
            continue
        x1, y1 = positions[node]
        for parent in parents:
            if parent not in positions:
                continue
            x0, y0 = positions[parent]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line=dict(width=1.5, color="#b0b0b0"),
        hoverinfo="none",
        showlegend=False,
    )

    node_x, node_y, colors, labels, hover = [], [], [], [], []
    for node_id, (x, y) in positions.items():
        exp = experiments.get(node_id)
        node_x.append(x)
        node_y.append(y)
        status = exp.conclusion.status if exp else "draft"
        colors.append(_STATUS_COLORS.get(status, "#9e9e9e"))
        labels.append(exp.title if exp else node_id)
        hover.append(
            f"{exp.title}<br>id: {exp.id}<br>branche: {exp.branch}<br>"
            f"statut: {exp.conclusion.status}<br>intention: {exp.intent}"
            if exp
            else node_id
        )

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=labels,
        textposition="top center",
        hovertext=hover,
        hoverinfo="text",
        marker=dict(size=20, color=colors, line=dict(width=1, color="#333333")),
        showlegend=False,
    )

    tip_x, tip_y, tip_text = [], [], []
    for branch_name, exp_id in repo.branches.items():
        if exp_id not in positions:
            continue
        x, y = positions[exp_id]
        tip_x.append(x)
        tip_y.append(y - 0.3)
        tip_text.append(f"⌥ {branch_name}")

    branch_trace = go.Scatter(
        x=tip_x,
        y=tip_y,
        mode="text",
        text=tip_text,
        textfont=dict(color=_BRANCH_LABEL_COLOR, size=11),
        hoverinfo="none",
        showlegend=False,
    )

    fig = go.Figure(data=[edge_trace, node_trace, branch_trace])
    fig.update_layout(
        title="Follow — graphe de filiation",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, autorange="reversed"),
        plot_bgcolor="white",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def render_graph_html(repo: "Repository", path: str | Path, *, embed: bool = True) -> Path:
    """Write the lineage graph to a single self-contained HTML file (Plotly, no Graphviz
    binary or other system dependency needed) and return the path written to.
    """
    out = Path(path)
    build_graph_figure(repo).write_html(str(out), include_plotlyjs=True if embed else "cdn")
    return out
