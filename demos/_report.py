"""Shared visual shell for Follow demo reports (see demos/README.md).

Each demo script builds its own body sections as plain HTML strings using the CSS vocabulary
defined here (``.section``, ``.trial-card``, ``.res-row``/``.resolution-list``, ``.fiche-card``,
``.repro``, ...) and calls :func:`render_report` to wrap them in a themed, self-contained page.
Keeping the shell in one place means every demo reads as one consistent product instead of a
one-off page each time.
"""

from __future__ import annotations

_FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Archivo:wght@600;700;800&"
    "family=Public+Sans:ital,wght@0,400;0,500;0,600;1,400&"
    "family=IBM+Plex+Mono:wght@400;500;600&display=swap"
)

_STYLE = """
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
    accent and the verdict-label color.
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
) -> str:
    """The merge/final-commit fiche panel. ``parents`` is a list of (role, branch, label)."""
    badges_html = "\n          ".join(f'<span class="badge">{b}</span>' for b in badges)
    pills_html = "\n          ".join(
        f'<div class="parent-pill"><span class="role">{role} · {branch_name}</span><span class="lbl">{label}</span></div>'
        for role, branch_name, label in parents
    )
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
      </div>

      <div class="fiche-row">
        <div class="fiche-label">Parents (commit de fusion — deux ascendances)</div>
        <div class="parent-pills">
          {pills_html}
        </div>
      </div>

      <div class="fiche-row">
        <div class="fiche-label">Conclusion</div>
        <p class="fiche-text">{conclusion}</p>
      </div>
    </div>"""


def render_report(
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
    """Assemble a themed, self-contained demo page from pre-rendered section HTML.

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
<style>{_STYLE}</style>

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
