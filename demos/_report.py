"""Thin re-export: the actual theme now lives in :mod:`follow.report` (a first-class library
feature, not a demo-only concern) so that ``follow report``/``render_study_html`` and these
hand-curated demos share one visual system. Kept so existing demo scripts don't need to change
their imports.
"""

from __future__ import annotations

from follow.report import (
    THEME_CSS,
    batch_table,
    experiment_fiche,
    fiche_card,
    objectives_table,
    render_page as render_report,
    resolution_conflict_row,
    resolution_plain_row,
    results_table,
    trial_card,
)

__all__ = [
    "THEME_CSS",
    "batch_table",
    "experiment_fiche",
    "fiche_card",
    "objectives_table",
    "render_report",
    "resolution_conflict_row",
    "resolution_plain_row",
    "results_table",
    "trial_card",
]
