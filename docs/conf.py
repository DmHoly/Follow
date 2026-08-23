"""Sphinx configuration for Follow's documentation. Build with:

    pip install -e ".[docs]"
    sphinx-build -b html docs docs/_build/html
"""

from __future__ import annotations

import follow

project = "Follow"
copyright = "2026, DmHoly"
author = "DmHoly"
release = follow.__version__
version = release

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest", None),
}

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}

templates_path: list[str] = []
exclude_patterns: list[str] = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path: list[str] = []
html_title = f"Follow {release}"
