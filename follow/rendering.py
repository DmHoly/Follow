from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .diffing import StructureDiff, diff_structures
from .formatting import format_value, is_quantity_leaf
from .models import Experiment

if TYPE_CHECKING:
    from .repository import Repository


def _render_structure_lines(value: Any, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    lines: list[str] = []
    if is_quantity_leaf(value):
        return [f"{prefix}{format_value(value)}"]
    if isinstance(value, dict):
        for key in value:
            child = value[key]
            if isinstance(child, (dict, list)) and not is_quantity_leaf(child):
                lines.append(f"{prefix}- **{key}**:")
                lines.extend(_render_structure_lines(child, indent + 1))
            else:
                lines.append(f"{prefix}- **{key}**: {format_value(child)}")
        return lines
    if isinstance(value, list):
        for i, item in enumerate(value):
            if isinstance(item, (dict, list)) and not is_quantity_leaf(item):
                lines.append(f"{prefix}- [{i}]:")
                lines.extend(_render_structure_lines(item, indent + 1))
            else:
                lines.append(f"{prefix}- [{i}]: {format_value(item)}")
        return lines
    return [f"{prefix}{value}"]


def render_fiche(experiment: Experiment, repo: "Repository") -> str:
    """Render a Markdown "fiche" for one committed experiment: intent, structure (with the
    diff against its baseline when it has one), protocol, objectives, evidence and conclusion.
    This is Follow's answer to `git show`.
    """
    lines: list[str] = []
    lines.append(f"# {experiment.title}")
    lines.append("")
    lines.append(f"- **id**: `{experiment.id}`")
    lines.append(f"- **branch**: `{experiment.branch}`")
    if experiment.parents:
        lines.append(f"- **parents**: {', '.join(f'`{p}`' for p in experiment.parents)}")
    if experiment.author:
        lines.append(f"- **author**: {experiment.author}")
    lines.append(f"- **created_at**: {experiment.created_at.isoformat()}")
    lines.append(f"- **status**: {experiment.conclusion.status}")
    if experiment.tags:
        lines.append(f"- **tags**: {', '.join(experiment.tags)}")
    lines.append("")

    lines.append("## Intention")
    lines.append("")
    lines.append(experiment.intent)
    if experiment.hypothesis:
        lines.append("")
        lines.append(f"*Hypothèse : {experiment.hypothesis}*")
    lines.append("")

    if experiment.references:
        lines.append("## Références")
        lines.append("")
        for ref in experiment.references:
            target = f"`{ref.experiment_id}`" if ref.experiment_id else (ref.external_source or "?")
            note = f" — {ref.note}" if ref.note else ""
            lines.append(f"- **{ref.role}** ({ref.label}): {target}{note}")
        lines.append("")

    lines.append("## Structure")
    lines.append("")
    lines.append(f"*type*: `{experiment.structure_type}`")
    lines.append("")
    lines.extend(_render_structure_lines(experiment.structure))
    lines.append("")

    baseline = next((r for r in experiment.references if r.role == "baseline" and r.experiment_id), None)
    if baseline is not None:
        try:
            parent = repo.get(baseline.experiment_id)
            parent_structure = repo.load_structure(parent)
            this_structure = repo.load_structure(experiment)
            diff = diff_structures(parent_structure, this_structure)
        except KeyError:
            diff = None
        if diff:
            lines.append(f"### Paramètres modifiés par rapport à la référence (`{baseline.experiment_id}`)")
            lines.append("")
            for entry in diff:
                lines.append(f"- {entry}")
            lines.append("")

    if experiment.steps:
        lines.append("## Étapes")
        lines.append("")
        for step in sorted(experiment.steps, key=lambda s: s.order):
            lines.append(f"{step.order}. **{step.name}**" + (f" — {step.description}" if step.description else ""))
            for key, quantity in step.parameters.items():
                lines.append(f"   - {key}: {quantity}")
        lines.append("")

    if experiment.objectives:
        lines.append("## Objectifs")
        lines.append("")
        results_by_name = {r.objective: r for r in experiment.conclusion.objective_results}
        for objective in experiment.objectives:
            target_bits = []
            if objective.target is not None:
                target_bits.append(f"target={objective.target}")
            if objective.tolerance is not None:
                target_bits.append(f"± {objective.tolerance}")
            if objective.range is not None:
                target_bits.append(f"range={objective.range}")
            target_desc = ", ".join(target_bits) or "—"
            lines.append(f"- **{objective.name}** ({objective.direction}, {target_desc})")
            result = results_by_name.get(objective.name)
            if result is not None:
                observed = f", observé={result.observed}" if result.observed else ""
                lines.append(f"  → **{result.status}**{observed}")
                if result.reasoning:
                    lines.append(f"  {result.reasoning}")
        lines.append("")

    if experiment.evidence:
        lines.append("## Preuves")
        lines.append("")
        for item in experiment.evidence:
            lines.append(f"- `{item.id}` — {item.description} (source: {item.source})")
            for key, quantity in item.metrics.items():
                lines.append(f"  - {key}: {quantity}")
        lines.append("")

    lines.append("## Conclusion")
    lines.append("")
    lines.append(f"- **statut**: {experiment.conclusion.status}")
    if experiment.conclusion.decision:
        lines.append(f"- **décision**: {experiment.conclusion.decision}")
    if experiment.conclusion.summary:
        lines.append("")
        lines.append(experiment.conclusion.summary)
    lines.append("")

    return "\n".join(lines)


def render_log(repo: "Repository", ref: str) -> str:
    """A `git log --oneline`-style history of one branch/tag/experiment's lineage."""
    lines = []
    for exp in repo.log(ref):
        lines.append(f"{exp.id}  ({exp.branch})  {exp.title}  [{exp.conclusion.status}]")
    return "\n".join(lines)


def render_dot(repo: "Repository") -> str:
    """The full experiment graph (lineage + branch tips) as Graphviz DOT source."""
    lines = ["digraph follow {", '  rankdir="BT";', "  node [shape=box, fontname=\"monospace\"];"]
    for exp in repo:
        label = f"{exp.title}\\n{exp.id}".replace('"', '\\"')
        lines.append(f'  "{exp.id}" [label="{label}"];')
        for parent in exp.parents:
            lines.append(f'  "{exp.id}" -> "{parent}";')
    for name, exp_id in repo.branches.items():
        node = f"branch:{name}"
        lines.append(f'  "{node}" [shape=note, style=filled, fillcolor=lightyellow, label="{name}"];')
        lines.append(f'  "{node}" -> "{exp_id}" [style=dashed];')
    lines.append("}")
    return "\n".join(lines)
