"""The exact same repository as demos/chocolate_fondant.py, rendered by the fully automatic
follow.render_study_html instead of hand-curated sections - compare the two output files to see
what `follow report` gives you for free versus a demo someone spent time narrating.

Run: python -m demos.auto_report [--out demos/output/chocolate_fondant_auto_report.html] [--embed]
"""

from __future__ import annotations

from demos._main import run_demo
from demos.chocolate_fondant import build_repository
from follow import render_study_html


def _render(repo, *, embed_plotly: bool) -> str:
    return render_study_html(
        repo,
        title="Fondant au chocolat cœur coulant — rapport automatique",
        description="Généré par render_study_html (follow report), sans aucune section écrite à la main.",
        embed_plotly=embed_plotly,
    )


def main() -> None:
    run_demo(
        doc=__doc__,
        default_out="demos/output/chocolate_fondant_auto_report.html",
        build_repository=build_repository,
        render=_render,
    )


if __name__ == "__main__":
    main()
