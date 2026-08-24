"""The command-line wrapper every demo script shares.

Each demo used to carry its own copy of the same ``main()``: build the parser, add ``--out`` and
``--embed``, build the repository, render it, create the parent directory, write the file, print
the size. Six identical copies differing only in the default output path - so the copy lives here
once, and each demo passes the two things that are actually its own.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from follow import Repository


def run_demo(
    *,
    doc: str | None,
    default_out: str,
    build_repository: Callable[[], Repository],
    render: Callable[..., str],
    argv: list[str] | None = None,
) -> Path:
    """Parse ``--out``/``--embed``, render the demo, write it, and return the path written to."""
    parser = argparse.ArgumentParser(description=doc)
    parser.add_argument("--out", default=default_out)
    parser.add_argument(
        "--embed",
        action="store_true",
        help="embed plotly.js (~4.8MB, fully offline) instead of using the CDN",
    )
    args = parser.parse_args(argv)

    html = render(build_repository(), embed_plotly=args.embed)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return out
