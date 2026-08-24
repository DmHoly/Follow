"""The exact same repository as demos/chocolate_fondant.py, rendered by the fully automatic
follow.render_study_html instead of hand-curated sections - compare the two output files to see
what `follow report` gives you for free versus a demo someone spent time narrating.

Run: python -m demos.auto_report [--out demos/output/chocolate_fondant_auto_report.html] [--embed]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from demos.chocolate_fondant import build_repository
from follow import render_study_html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="demos/output/chocolate_fondant_auto_report.html")
    parser.add_argument("--embed", action="store_true", help="embed plotly.js (~4.8MB, fully offline) instead of using the CDN")
    args = parser.parse_args()

    repo = build_repository()
    html = render_study_html(
        repo,
        title="Fondant au chocolat cœur coulant — rapport automatique",
        description="Généré par render_study_html (follow report), sans aucune section écrite à la main.",
        embed_plotly=args.embed,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
