"""Themed, dependency-free HTML report generation - no AI, no template engine, just Python
f-strings over the data already sitting in a :class:`~follow.repository.Repository`.

Two layers:

- A small set of HTML building blocks (:func:`trial_card`, :func:`resolution_conflict_row`,
  :func:`resolution_plain_row`, :func:`fiche_card`, :func:`render_page`) that demo scripts can
  compose by hand for a curated narrative (see ``demos/``).
- :func:`render_study_html`, which builds a full "compte rendu d'étude" report straight from a
  Repository with no hand-authoring at all: every experiment becomes a card, and for merge
  commits the two parents are diffed against the result to show, path by path, which side each
  value was taken from - the same logic ``repo.diff``/``repo.diff_steps`` already expose.
"""

from __future__ import annotations

import html as _html
from typing import TYPE_CHECKING, Any

from .diffing import StructureDiff
from .formatting import format_value
from .graphing import build_graph_figure
from .merging import get_path, split_path
from .models import Experiment

if TYPE_CHECKING:
    from .repository import Repository

_FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Archivo:wght@600;700;800&"
    "family=Public+Sans:ital,wght@0,400;0,500;0,600;1,400&"
    "family=IBM+Plex+Mono:wght@400;500;600&display=swap"
)

THEME_CSS = """
:root {
  --bg: #F2F4EE;
  --surface: #FFFFFF;
  --surface-2: #E9EBE1;
  --ink: #1B231D;
  --ink-soft: #57604F;
  --ink-faint: #838C7C;
  --border: #D9DCCE;
  --accent: #B8791E;
  --accent-ink: #7A5416;
  --status-good: #2F7D4F;
  --status-explore: #2E6FA6;
  --status-bad: #B23B3B;
  --status-neutral: #8A8F80;
  --shadow: 0 1px 2px rgba(27,35,29,.04), 0 8px 24px -12px rgba(27,35,29,.12);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14181A; --surface: #1C2220; --surface-2: #262D29;
    --ink: #ECEFE6; --ink-soft: #A9B2A0; --ink-faint: #74806E; --border: #333D35;
    --accent: #E3A34E; --accent-ink: #EFC186;
    --status-good: #57B583; --status-explore: #6FA9D6; --status-bad: #E27E7E; --status-neutral: #9AA398;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 12px 28px -14px rgba(0,0,0,.55);
  }
}
:root[data-theme="dark"] {
  --bg: #14181A; --surface: #1C2220; --surface-2: #262D29;
  --ink: #ECEFE6; --ink-soft: #A9B2A0; --ink-faint: #74806E; --border: #333D35;
  --accent: #E3A34E; --accent-ink: #EFC186;
  --status-good: #57B583; --status-explore: #6FA9D6; --status-bad: #E27E7E; --status-neutral: #9AA398;
  --shadow: 0 1px 2px rgba(0,0,0,.3), 0 12px 28px -14px rgba(0,0,0,.55);
}

* { box-sizing: border-box; }
html { color-scheme: light dark; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 400 16px/1.5 "Public Sans", system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
::selection { background: var(--accent); color: #fff; }
a { color: var(--accent-ink); }
code { font-family: "IBM Plex Mono", monospace; font-size: .92em; }

.page { max-width: 1100px; margin: 0 auto; padding: 56px 24px 100px; display: flex; flex-direction: column; gap: 64px; }

.header { display: flex; flex-direction: column; gap: 18px; }
.eyebrow { font: 600 12px/1 "Public Sans", sans-serif; letter-spacing: .14em; text-transform: uppercase; color: var(--accent-ink); }
h1 { font: 800 clamp(30px, 4.2vw, 46px)/1.08 "Archivo", sans-serif; text-wrap: balance; margin: 0; letter-spacing: -.01em; }
.subtitle { font: 400 17px/1.6 "Public Sans", sans-serif; color: var(--ink-soft); max-width: 68ch; margin: 0; }
.stat-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 6px; }
.stat-chip { font: 500 13px/1 "IBM Plex Mono", monospace; padding: 9px 13px; border-radius: 8px;
  background: var(--surface); border: 1px solid var(--border); color: var(--ink-soft); box-shadow: var(--shadow); }
.stat-chip b { color: var(--ink); font-weight: 600; }

.section { display: flex; flex-direction: column; gap: 22px; }
.section-head { display: flex; flex-direction: column; gap: 8px; }
.section-label { font: 600 11px/1 "Public Sans", sans-serif; letter-spacing: .12em; text-transform: uppercase; color: var(--accent-ink); }
.section-title { font: 700 23px/1.25 "Archivo", sans-serif; margin: 0; text-wrap: balance; }
.section-desc { font: 400 15px/1.65 "Public Sans", sans-serif; color: var(--ink-soft); max-width: 74ch; margin: 0; }

.graph-frame { border: 1px solid var(--border); border-radius: 18px; background: var(--surface); padding: 20px; box-shadow: var(--shadow); }
.graph-inner { border-radius: 12px; overflow: hidden; border: 1px solid var(--border); background: #fff; }
.graph-inner .js-plotly-plot { width: 100% !important; }
.graph-legend { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 16px; padding: 0 4px; font: 500 12px/1 "IBM Plex Mono", monospace; color: var(--ink-soft); }
.legend-item { display: flex; align-items: center; gap: 7px; }
.legend-dot { width: 9px; height: 9px; border-radius: 50%; background: currentColor; flex: none; }
.legend-item.good { color: var(--status-good); }
.legend-item.explore { color: var(--status-explore); }
.legend-item.bad { color: var(--status-bad); }
.legend-item.neutral { color: var(--status-neutral); }

.trial-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
.trial-card { background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--status-explore);
  border-radius: 10px; padding: 18px 20px; display: flex; flex-direction: column; gap: 10px; box-shadow: var(--shadow); }
.trial-card[data-verdict="promote"] { border-left-color: var(--status-good); }
.trial-card[data-verdict="abandon"] { border-left-color: var(--status-bad); }
.trial-order { font: 600 11px/1 "IBM Plex Mono", monospace; color: var(--ink-faint); letter-spacing: .06em; text-transform: uppercase; }
.trial-temp { font: 700 28px/1 "Archivo", sans-serif; display: flex; align-items: baseline; gap: 8px; }
.trial-temp span { font: 500 13px "IBM Plex Mono", monospace; color: var(--ink-soft); }
.trial-meta { font: 400 13.5px/1.55 "Public Sans", sans-serif; color: var(--ink-soft); }
.trial-metric { font: 500 12.5px "IBM Plex Mono", monospace; color: var(--ink); display: flex; justify-content: space-between;
  border-top: 1px dashed var(--border); padding-top: 10px; }
.verdict-label { display: flex; align-items: center; gap: 7px; font: 600 11.5px "Public Sans", sans-serif; text-transform: uppercase; letter-spacing: .05em; }
.verdict-label.promote { color: var(--status-good); }
.verdict-label.branch { color: var(--status-explore); }
.verdict-label.abandon { color: var(--status-bad); }
.verdict-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

.resolution-list { display: flex; flex-direction: column; gap: 10px; }
.res-row { border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.res-row.plain { display: flex; align-items: center; gap: 12px; padding: 12px 20px; color: var(--ink-faint); font: 400 13.5px "Public Sans", sans-serif; flex-wrap: wrap; }
.res-row.plain .step-n { font: 600 12px "IBM Plex Mono", monospace; color: var(--ink-faint); }
.res-row.plain .no-conflict { margin-left: auto; font: 500 11px "IBM Plex Mono", monospace; text-transform: uppercase; letter-spacing: .06em; color: var(--status-neutral); }
.res-row.conflict { display: flex; flex-direction: column; gap: 14px; padding: 18px 20px 20px; box-shadow: var(--shadow); }
.res-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.res-head .step-n { font: 700 12.5px "IBM Plex Mono", monospace; color: var(--accent-ink); }
.res-head .step-name { font: 700 17px "Archivo", sans-serif; }
.res-sides { display: grid; grid-template-columns: 1fr auto 1fr; gap: 16px; align-items: stretch; }
.res-side { padding: 13px 15px; border-radius: 9px; background: var(--surface-2); border: 1.5px solid transparent; display: flex; flex-direction: column; gap: 5px; }
.res-side .src { font: 600 11px "Public Sans", sans-serif; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-faint); display: flex; justify-content: space-between; align-items: center; }
.res-side .val { font: 500 14px "IBM Plex Mono", monospace; color: var(--ink); }
.res-side .note { font: 400 12.5px/1.5 "Public Sans", sans-serif; color: var(--ink-soft); }
.res-side.winner { border-color: var(--status-good); background: var(--surface); }
.res-side.winner .src { color: var(--status-good); }
.res-check { font: 700 12px "IBM Plex Mono", monospace; }
.res-arrow { font: 700 20px "Archivo", sans-serif; color: var(--ink-faint); display: flex; align-items: center; justify-content: center; padding-top: 18px; }
.res-flag { align-self: flex-start; font: 500 12px "IBM Plex Mono", monospace; color: var(--accent-ink); background: var(--surface-2); padding: 5px 11px; border-radius: 6px; }

.fiche-card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 26px 28px;
  display: flex; flex-direction: column; gap: 20px; box-shadow: var(--shadow); }
.fiche-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.fiche-title { font: 700 21px "Archivo", sans-serif; margin: 0 0 6px; }
.fiche-id { font: 500 12.5px "IBM Plex Mono", monospace; color: var(--ink-faint); }
.fiche-badges { display: flex; gap: 8px; flex-wrap: wrap; }
.badge { font: 600 11px "Public Sans", sans-serif; text-transform: uppercase; letter-spacing: .05em; padding: 6px 11px;
  border-radius: 999px; border: 1px solid var(--status-good); color: var(--status-good); }
.badge.neutral { border-color: var(--status-neutral); color: var(--status-neutral); }
.fiche-row { display: flex; flex-direction: column; gap: 6px; }
.fiche-label { font: 600 11px "Public Sans", sans-serif; text-transform: uppercase; letter-spacing: .08em; color: var(--ink-faint); }
.fiche-text { font: 400 14.5px/1.6 "Public Sans", sans-serif; color: var(--ink); max-width: 74ch; }
.parent-pills, .ref-pills { display: flex; gap: 10px; flex-wrap: wrap; }
.parent-pill { display: flex; flex-direction: column; gap: 2px; padding: 9px 13px; border-radius: 9px; background: var(--surface-2); font: 500 12px "IBM Plex Mono", monospace; }
.parent-pill .role { font: 600 10.5px "Public Sans", sans-serif; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-faint); }
.parent-pill .lbl { color: var(--ink); }

.source-table { width: 100%; border-collapse: collapse; font: 400 13.5px/1.5 "Public Sans", sans-serif; }
.source-table th { text-align: left; font: 600 11px "Public Sans", sans-serif; text-transform: uppercase; letter-spacing: .05em;
  color: var(--ink-faint); padding: 0 14px 10px 0; border-bottom: 1px solid var(--border); }
.source-table td { padding: 11px 14px 11px 0; border-bottom: 1px solid var(--border); vertical-align: top; color: var(--ink-soft); }
.source-table td:first-child { color: var(--ink); font-weight: 500; }
.source-table tr:last-child td { border-bottom: none; }
.table-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 14px; background: var(--surface); box-shadow: var(--shadow); padding: 4px 20px; }

.diff-list { display: flex; flex-direction: column; gap: 4px; }
.diff-line { font: 500 12.5px "IBM Plex Mono", monospace; color: var(--ink-soft); }
.diff-line.added { color: var(--status-good); }
.diff-line.removed { color: var(--status-bad); }

.repro { background: #1B2320; color: #D8E0D6; border-radius: 14px; padding: 22px 24px;
  font: 400 13px/1.85 "IBM Plex Mono", monospace; overflow-x: auto; box-shadow: var(--shadow); }
.repro .cmt { color: #7C8A79; }
.repro .cmd::before { content: "$ "; color: #7C8A79; }
.credit { font: 400 12.5px "Public Sans", sans-serif; color: var(--ink-faint); }

@media (max-width: 640px) {
  .res-sides { grid-template-columns: 1fr; }
  .res-arrow { padding-top: 0; }
  .fiche-top { flex-direction: column; }
}
"""


def _esc(value: Any) -> str:
    """Escape arbitrary repository data before it goes into an HTML page - unlike the demo
    scripts (which only ever feed these builders their own trusted, hand-written strings),
    :func:`render_study_html` renders free text a repository's authors typed, so it must not be
    trusted as HTML.
    """
    return _html.escape(str(value), quote=True)


def trial_card(
    *,
    order_label: str,
    exp_id: str,
    headline: str,
    headline_unit: str,
    meta: str,
    metric_label: str,
    metric_value: str,
    verdict: str,
    verdict_label: str,
) -> str:
    """One card in a ``.trial-grid``: a single branch commit being tested against the baseline.
    ``verdict`` is one of ``promote``/``branch``/``abandon`` and drives both the left border
    accent and the verdict-label color. Callers are responsible for escaping any untrusted text
    they pass in - this builder treats every argument as HTML.
    """
    return f"""      <div class="trial-card" data-verdict="{verdict}">
        <div class="trial-order">{order_label} · {exp_id[:12]}</div>
        <div class="trial-temp">{headline} <span>{headline_unit}</span></div>
        <div class="trial-meta">{meta}</div>
        <div class="trial-metric"><span>{metric_label}</span><span>{metric_value}</span></div>
        <div class="verdict-label {verdict}"><span class="verdict-dot"></span>{verdict_label}</div>
      </div>"""


def resolution_plain_row(step_index: int, step_name: str, note: str = "identique des deux côtés") -> str:
    """A step with no conflict: same value on both sides, nothing to resolve."""
    return (
        f'      <div class="res-row plain"><span class="step-n">[{step_index}]</span> {step_name} '
        f'<span class="no-conflict">{note}</span></div>'
    )


def resolution_conflict_row(
    *,
    step_index: int,
    step_name: str,
    left_src: str,
    left_val: str,
    left_note: str,
    right_src: str,
    right_val: str,
    right_note: str,
    winner: str,
    flag_text: str,
    arrow: str = "≠",
) -> str:
    """A step that differs between the two lines being merged, with the resolution made explicit.
    ``winner`` is ``"left"`` or ``"right"`` - that side gets the "✓ retenu" tag and border.
    """
    left_winner = winner == "left"
    return f"""      <div class="res-row conflict">
        <div class="res-head">
          <span class="step-n">[{step_index}]</span>
          <span class="step-name">{step_name}</span>
        </div>
        <div class="res-sides">
          <div class="res-side{' winner' if left_winner else ''}">
            <div class="src">{left_src}{' <span class="res-check">✓ retenu</span>' if left_winner else ''}</div>
            <div class="val">{left_val}</div>
            <div class="note">{left_note}</div>
          </div>
          <div class="res-arrow">{arrow}</div>
          <div class="res-side{'' if left_winner else ' winner'}">
            <div class="src">{right_src}{'' if left_winner else ' <span class="res-check">✓ retenu</span>'}</div>
            <div class="val">{right_val}</div>
            <div class="note">{right_note}</div>
          </div>
        </div>
        <div class="res-flag">{flag_text}</div>
      </div>"""


def fiche_card(
    *,
    fiche_title: str,
    exp_id: str,
    branch: str,
    badges: list[str],
    intent: str,
    parents: list[tuple[str, str, str]],
    conclusion: str,
    parents_label: str = "Parents (commit de fusion — deux ascendances)",
) -> str:
    """One experiment's fiche panel. ``parents`` is a list of (role, branch, label); pass an
    empty list to omit the row entirely (a root experiment has none).
    """
    badges_html = "\n          ".join(f'<span class="badge">{b}</span>' for b in badges)
    parents_row = ""
    if parents:
        pills_html = "\n          ".join(
            f'<div class="parent-pill"><span class="role">{role} · {branch_name}</span><span class="lbl">{label}</span></div>'
            for role, branch_name, label in parents
        )
        parents_row = f"""

      <div class="fiche-row">
        <div class="fiche-label">{parents_label}</div>
        <div class="parent-pills">
          {pills_html}
        </div>
      </div>"""
    return f"""    <div class="fiche-card">
      <div class="fiche-top">
        <div>
          <div class="fiche-title">{fiche_title}</div>
          <div class="fiche-id">{exp_id} · branche {branch}</div>
        </div>
        <div class="fiche-badges">
          {badges_html}
        </div>
      </div>

      <div class="fiche-row">
        <div class="fiche-label">Intention</div>
        <p class="fiche-text">{intent}</p>
      </div>{parents_row}

      <div class="fiche-row">
        <div class="fiche-label">Conclusion</div>
        <p class="fiche-text">{conclusion}</p>
      </div>
    </div>"""


def render_page(
    *,
    title: str,
    description: str,
    eyebrow: str,
    heading: str,
    subtitle: str,
    stat_chips: list[str],
    sections: list[str],
    footer: str,
) -> str:
    """Assemble a themed, self-contained page from pre-rendered section HTML.

    ``stat_chips`` are raw inner-HTML strings for ``.stat-chip`` spans; ``sections`` and
    ``footer`` are raw ``<section class="section">...</section>``/``<footer>...</footer>``
    blocks the caller builds with the CSS vocabulary above.
    """
    chips = "\n".join(f'      <span class="stat-chip">{c}</span>' for c in stat_chips)
    body_sections = "\n\n".join(sections)
    return f"""<title>{title}</title>
<meta name="description" content="{description}" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{_FONTS}" rel="stylesheet">
<style>{THEME_CSS}</style>

<div class="page">
  <header class="header">
    <div class="eyebrow">{eyebrow}</div>
    <h1>{heading}</h1>
    <p class="subtitle">{subtitle}</p>
    <div class="stat-row">
{chips}
    </div>
  </header>

{body_sections}

{footer}
</div>
"""


# ---------------------------------------------------------------------------------
# Fully automatic study report: no hand-authored sections, everything below is derived
# straight from Repository/Experiment data.
# ---------------------------------------------------------------------------------

_DECISION_LABELS = {
    "promote": "promote",
    "branch": "branch (exploration)",
    "replicate": "replicate",
    "abandon": "abandon",
    "inconclusive": "inconclusive",
}


def _diff_line_html(prefix: str, entry) -> str:
    if entry.kind == "added":
        text = f"+ {prefix}{_esc(entry.path)}: {_esc(format_value(entry.after))}"
    elif entry.kind == "removed":
        text = f"- {prefix}{_esc(entry.path)}: {_esc(format_value(entry.before))}"
    else:
        text = f"~ {prefix}{_esc(entry.path)}: {_esc(format_value(entry.before))} → {_esc(format_value(entry.after))}"
    return f'<div class="diff-line {entry.kind}">{text}</div>'


def _lineage_html(repo: "Repository", exp: Experiment) -> str:
    """What changed since this experiment's parent(s) - a diff summary for 1 parent, or a
    per-path attribution (which parent each value came from) for a 2-parent merge commit.
    """
    if len(exp.parents) == 2 and exp.parents[0] in repo and exp.parents[1] in repo:
        return _merge_attribution_html(repo, exp)
    if len(exp.parents) == 1 and exp.parents[0] in repo:
        return _single_parent_diff_html(repo, exp)
    return ""


def _single_parent_diff_html(repo: "Repository", exp: Experiment) -> str:
    parent = repo.get(exp.parents[0])
    lines: list[str] = []
    try:
        for entry in repo.diff(parent.id, exp.id):
            lines.append(_diff_line_html("", entry))
    except KeyError:
        pass
    for entry in repo.diff_steps(parent.id, exp.id):
        lines.append(_diff_line_html("steps", entry))
    if not lines:
        return ""
    return (
        '    <div class="fiche-row">\n'
        f'      <div class="fiche-label">Changements depuis le parent ({_esc(parent.id[:12])} — {_esc(parent.title)})</div>\n'
        '      <div class="diff-list">\n        ' + "\n        ".join(lines) + "\n      </div>\n    </div>"
    )


def _merge_attribution_html(repo: "Repository", exp: Experiment) -> str:
    a, b = repo.get(exp.parents[0]), repo.get(exp.parents[1])
    rows: list[str] = []
    idx = 0

    for kind, differ in (("structure", repo.diff), ("steps", repo.diff_steps)):
        try:
            diff_ab = differ(a.id, b.id)
        except KeyError:
            continue
        if not diff_ab:
            continue
        if kind == "structure":
            merged_dump: Any = repo.load_structure(exp).model_dump(mode="json")
        else:
            merged_dump = [s.model_dump(mode="json") for s in exp.steps]
        for entry in diff_ab:
            tokens = split_path(entry.path)
            try:
                merged_value = get_path(merged_dump, tokens)
            except (KeyError, IndexError, TypeError):
                merged_value = None
            if entry.path.startswith("["):
                label = f"{kind}{entry.path}"
            elif entry.path:
                label = f"{kind}.{entry.path}"
            else:
                label = kind
            if merged_value == entry.before:
                rows.append(
                    resolution_conflict_row(
                        step_index=idx, step_name=_esc(label),
                        left_src=_esc(a.branch), left_val=_esc(format_value(entry.before)), left_note=f"{_esc(a.id[:12])} — {_esc(a.title)}",
                        right_src=_esc(b.branch), right_val=_esc(format_value(entry.after)), right_note=f"{_esc(b.id[:12])} — {_esc(b.title)}",
                        winner="left", flag_text="valeur conservée du premier parent", arrow="≠",
                    )
                )
            elif merged_value == entry.after:
                rows.append(
                    resolution_conflict_row(
                        step_index=idx, step_name=_esc(label),
                        left_src=_esc(a.branch), left_val=_esc(format_value(entry.before)), left_note=f"{_esc(a.id[:12])} — {_esc(a.title)}",
                        right_src=_esc(b.branch), right_val=_esc(format_value(entry.after)), right_note=f"{_esc(b.id[:12])} — {_esc(b.title)}",
                        winner="right", flag_text="valeur reprise du second parent", arrow="→",
                    )
                )
            else:
                rows.append(resolution_plain_row(idx, f"{_esc(label)} — valeur propre à la fusion", note=_esc(format_value(merged_value))))
            idx += 1

    if not rows:
        return ""
    return (
        '    <div class="fiche-row">\n'
        f'      <div class="fiche-label">Résolution de la fusion ({_esc(a.branch)} + {_esc(b.branch)})</div>\n'
        '      <div class="resolution-list">\n' + "\n".join(rows) + "\n      </div>\n    </div>"
    )


def _objectives_html(exp: Experiment) -> str:
    if not exp.objectives:
        return ""
    results_by_name = {r.objective: r for r in exp.conclusion.objective_results}
    lines = []
    for objective in exp.objectives:
        result = results_by_name.get(objective.name)
        status = f" → <strong>{_esc(result.status)}</strong>" if result else ""
        observed = f" (observé : {_esc(format_value(result.observed.model_dump(mode='json')))})" if result and result.observed else ""
        lines.append(f"<div>{_esc(objective.name)} ({_esc(objective.direction)}){status}{observed}</div>")
    return (
        '    <div class="fiche-row">\n      <div class="fiche-label">Objectifs</div>\n      <div class="fiche-text">'
        + "".join(lines)
        + "</div>\n    </div>"
    )


def _evidence_html(exp: Experiment) -> str:
    if not exp.evidence:
        return ""
    lines = [
        f"<div>{_esc(e.description)} — {_esc(e.source)}"
        + "".join(f" · {_esc(k)}: {_esc(format_value(v.model_dump(mode='json')))}" for k, v in e.metrics.items())
        + "</div>"
        for e in exp.evidence
    ]
    return (
        '    <div class="fiche-row">\n      <div class="fiche-label">Preuves</div>\n      <div class="fiche-text">'
        + "".join(lines)
        + "</div>\n    </div>"
    )


def _experiment_section(repo: "Repository", exp: Experiment, index: int, total: int) -> str:
    badges = [exp.conclusion.status]
    if exp.conclusion.decision:
        badges.append(_DECISION_LABELS.get(exp.conclusion.decision, exp.conclusion.decision))
    badges = [_esc(b) for b in badges]

    parents = [
        ("parent", repo.get(p).branch if p in repo else "?", f"{p[:12]} — {repo.get(p).title if p in repo else 'introuvable'}")
        for p in exp.parents
    ]
    parents = [(_esc(role), _esc(branch), _esc(label)) for role, branch, label in parents]
    parents_label = "Filiation (fusion)" if len(exp.parents) == 2 else "Filiation"

    card = fiche_card(
        fiche_title=_esc(exp.title),
        exp_id=_esc(exp.id),
        branch=_esc(exp.branch),
        badges=badges,
        intent=_esc(exp.intent),
        parents=parents,
        parents_label=parents_label,
        conclusion=_esc(exp.conclusion.summary) if exp.conclusion.summary else "—",
    )
    extra = "\n".join(part for part in (_lineage_html(repo, exp), _objectives_html(exp), _evidence_html(exp)) if part)
    if extra:
        card = card[: -len("\n    </div>")] + "\n" + extra + "\n    </div>"

    return f"""  <section class="section" id="{_esc(exp.id)}">
    <div class="section-head">
      <div class="section-label">Commit {index} / {total} · {_esc(exp.branch)}</div>
      <h2 class="section-title">{_esc(exp.title)}</h2>
    </div>
{card}
  </section>"""


def _index_html(experiments: list[Experiment]) -> str:
    rows = "\n".join(
        f'          <tr><td><a href="#{_esc(e.id)}">{_esc(e.title)}</a></td>'
        f"<td>{_esc(e.branch)}</td><td>{_esc(e.id[:12])}</td>"
        f"<td>{_esc(e.conclusion.status)}{' · ' + _esc(e.conclusion.decision) if e.conclusion.decision else ''}</td></tr>"
        for e in experiments
    )
    return f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Sommaire</div>
      <h2 class="section-title">{len(experiments)} commits</h2>
    </div>
    <div class="table-scroll">
      <table class="source-table">
        <thead><tr><th>Titre</th><th>Branche</th><th>id</th><th>Statut</th></tr></thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
  </section>"""


def render_study_html(
    repo: "Repository",
    *,
    ref: str | None = None,
    title: str = "Compte rendu d'étude",
    description: str = "Rapport généré automatiquement par Follow, sans intervention manuelle.",
    embed_plotly: bool = True,
) -> str:
    """Render an entire study as a themed HTML report, generated purely from repository data.

    No AI, no hand-authored narrative: every experiment becomes a section built from its own
    fields, and every merge commit is explained by diffing each of its two parents against the
    result (:meth:`~follow.repository.Repository.diff`/``diff_steps``) to show, path by path,
    which parent each value was taken from. Pass ``ref`` to report on one branch/tag's lineage
    (:meth:`Repository.log`); omit it to report on the whole repository, oldest commit first.
    """
    if ref is not None:
        experiments = list(reversed(repo.log(ref)))
    else:
        experiments = sorted(repo, key=lambda e: e.created_at)

    merges = sum(1 for e in experiments if len(e.parents) == 2)
    stat_chips = [
        f"<b>{len(experiments)}</b> commits",
        f"<b>{len(repo.branches)}</b> branches",
        f"<b>{merges}</b> fusions",
    ]
    if repo.tags:
        stat_chips.append(f"<b>{len(repo.tags)}</b> tags")

    graph_html = ""
    try:
        fig = build_graph_figure(repo)
        plot_html = fig.to_html(
            include_plotlyjs=True if embed_plotly else "cdn",
            full_html=False,
            div_id="follow-graph",
            config={"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["toImage"]},
        )
        graph_html = f"""  <section class="section">
    <div class="section-head">
      <div class="section-label">Graphe de filiation</div>
      <h2 class="section-title">follow graph</h2>
    </div>
    <div class="graph-frame">
      <div class="graph-inner">
        {plot_html}
      </div>
    </div>
  </section>"""
    except Exception:
        graph_html = ""

    sections = [s for s in [_index_html(experiments), graph_html] if s]
    sections += [_experiment_section(repo, exp, i + 1, len(experiments)) for i, exp in enumerate(experiments)]

    footer = (
        '<footer class="footer section"><p class="credit">'
        "Généré automatiquement par <code>follow report</code> — aucune synthèse, "
        "uniquement les données du dépôt.</p></footer>"
    )

    return render_page(
        title=title,
        description=description,
        eyebrow="Follow · compte rendu d'étude",
        heading=title,
        subtitle=description,
        stat_chips=stat_chips,
        sections=sections,
        footer=footer,
    )
