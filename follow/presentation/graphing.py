from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

import plotly.graph_objects as go

from ..core.errors import FollowError

if TYPE_CHECKING:
    from ..storage.repository import Repository

_STATUS_COLORS = {
    "draft": "#9e9e9e",
    "running": "#1f77b4",
    "concluded": "#2ca02c",
    "abandoned": "#d62728",
}
_BRANCH_LABEL_COLOR = "#8a6d00"


def _depths(dag: dict[str, list[str]]) -> dict[str, int]:
    """Longest-path-from-a-root depth for each node, used as the layer/row of a layered layout.

    Computed by topological (Kahn) traversal rather than recursion. A recursive walk here recursed
    once per generation, so its stack depth was the length of the lineage - and, because it
    memoised as it went, whether it stayed flat or went all the way down depended on the order the
    dict happened to be iterated in. That order comes from ``objects_dir.glob("*.json")`` on load,
    which is not guaranteed: the same repository could render fine in one process and raise
    ``RecursionError`` in the next. Iteration removes the failure mode entirely, whatever the
    order.

    A cycle raises :class:`~follow.storage.repository.FollowError`. Lineage cycles cannot occur in a
    healthy repository (a commit's id is derived from content that already includes its parents,
    so a parent always exists before its child), which is exactly why one means the repository is
    corrupt - and drawing a plausible-looking graph with silently wrong depths, as the previous
    cycle "guard" did, hides that.
    """
    parents = {node: [p for p in dag.get(node, []) if p in dag] for node in dag}
    children: dict[str, list[str]] = {node: [] for node in dag}
    for node, node_parents in parents.items():
        for parent in node_parents:
            children[parent].append(node)

    remaining = {node: len(node_parents) for node, node_parents in parents.items()}
    queue = deque(sorted(node for node, count in remaining.items() if count == 0))
    depths = dict.fromkeys(dag, 0)

    resolved = 0
    while queue:
        node = queue.popleft()
        resolved += 1
        for child in children[node]:
            depths[child] = max(depths[child], depths[node] + 1)
            remaining[child] -= 1
            if remaining[child] == 0:
                queue.append(child)

    if resolved != len(dag):
        stuck = sorted(node for node, count in remaining.items() if count > 0)
        raise FollowError(
            f"lineage cycle in the experiment graph, involving {stuck[:5]}"
            f"{' and others' if len(stuck) > 5 else ''} - an experiment cannot descend from "
            "itself, so this repository's parent links are corrupt and no ordering of them exists"
        )
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
            def barycenter(node: str) -> float:
                xs = [positions[p][0] for p in dag.get(node, []) if p in positions]
                return sum(xs) / len(xs) if xs else 0.0

            nodes.sort(key=barycenter)
        offset = (len(nodes) - 1) / 2
        for i, node in enumerate(nodes):
            positions[node] = (i - offset, float(d))
    return positions


def build_graph_figure(repo: "Repository", *, dag: dict[str, list[str]] | None = None) -> go.Figure:
    """The full lineage graph as a Plotly figure: one marker per experiment, an edge per
    parent link, and a label at each branch tip - Follow's lightweight, dependency-light
    stand-in for a Graphviz rendering.

    `dag` defaults to `repo.graph()` (every experiment in the repository). Pass a filtered or
    contracted `{id: [parent_ids]}` mapping instead to draw a subset of the lineage - e.g. a
    caller that only cares about some domain-specific notion of a "significant" commit can
    collapse the rest out and reconnect the edges itself; Follow only draws whatever graph it's
    given; nodes not present in `dag` are simply skipped, so any parent still needs its own entry
    to be drawn (see the "a parent outside the dag is ignored" case in `_depths`).
    """
    if dag is None:
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

    # positions come from repo.graph(), which is built from these same experiments, so every
    # node id resolves - the previous `if exp else` fallbacks were unreachable
    node_x, node_y, colors, labels, hover = [], [], [], [], []
    for node_id, (x, y) in positions.items():
        exp = experiments[node_id]
        node_x.append(x)
        node_y.append(y)
        colors.append(_STATUS_COLORS.get(exp.conclusion.status, "#9e9e9e"))
        labels.append(exp.title)
        hover.append(
            f"{exp.title}<br>id: {exp.id}<br>branche: {exp.branch}<br>"
            f"statut: {exp.conclusion.status}<br>intention: {exp.intent}"
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
