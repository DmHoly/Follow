from __future__ import annotations

import hashlib
import json
from typing import Any

_PREFIXES = {
    "experiment": "exp",
    "evidence": "ev",
}


def content_id(kind: str, payload: dict[str, Any]) -> str:
    """A short content-addressed id, the same way git derives a commit sha from its content.

    Two objects with the same payload get the same id, which is what makes ids stable across
    reloads and lets the store deduplicate identical experiments the way git dedupes trees.
    """
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    prefix = _PREFIXES.get(kind, kind)
    return f"{prefix}_{digest}"
