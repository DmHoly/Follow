"""HTTP surface for Follow: a FastAPI app exposing :class:`follow.repository.Repository`
over REST, plus a small static GUI served from the same process (see :mod:`follow.api.app`).

Process control (start/stop/status as a background server) lives in :mod:`follow.api.server`
and is fronted by the ``follow_api`` console script (:mod:`follow.api.cli`).
"""

from __future__ import annotations
