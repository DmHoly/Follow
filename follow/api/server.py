"""Background process control for the Follow API: ``start``/``stop``/``status``, the machinery
behind the ``follow_api`` console script (:mod:`follow.api.cli`).

Only one server is tracked at a time (one pidfile, one metadata file, under
``~/.follow/api/``) - this mirrors the "single repository" scope of :func:`follow.api.app.create_app`:
one ``follow_api start`` serves one repository, and ``stop``/``status`` need no arguments because
there is only ever the one to ask about.

The server itself runs as a detached child process (``python -m follow.api.server _run``, reading
its configuration from environment variables) so it keeps running after the parent CLI invocation
exits - the same shape as a classic Unix daemon, without the double-fork: ``start_new_session=True``
already detaches it from the parent's session/controlling terminal, which is all that is needed
here (no chdir/umask dance, no need to survive the *parent's* controlling terminal closing versus
the parent process itself dying).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

STATE_DIR = Path.home() / ".follow" / "api"
PID_FILE = STATE_DIR / "server.pid"
META_FILE = STATE_DIR / "server.json"
LOG_FILE = STATE_DIR / "server.log"


class ServerError(Exception):
    """Raised for start/stop failures that are not simply "wasn't running"."""


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by someone else - treat as alive
    return True


def _read_meta() -> dict[str, Any] | None:
    if not PID_FILE.exists() or not META_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    if not _process_alive(pid):
        return None
    try:
        meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    meta["pid"] = pid
    return meta


def _clear_state() -> None:
    PID_FILE.unlink(missing_ok=True)
    META_FILE.unlink(missing_ok=True)


def status() -> dict[str, Any] | None:
    """The running server's metadata (pid, repo, host, port), or ``None`` if none is running.

    Also reconciles stale state: a pidfile left behind by a server that crashed or was killed
    out of band is cleaned up here rather than reported as "running".
    """
    meta = _read_meta()
    if meta is None:
        _clear_state()
        return None
    return meta


def _wait_for_health(host: str, port: int, timeout: float) -> bool:
    url = f"http://{host}:{port}/api/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:  # noqa: S310 - localhost only
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.2)
    return False


def start(
    repo_path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    structure_modules: tuple[str, ...] = (),
    startup_timeout: float = 10.0,
) -> dict[str, Any]:
    """Launch the API server as a detached background process serving ``repo_path``.

    Raises :class:`ServerError` if a server is already running (stop it first), or if it does
    not report healthy within ``startup_timeout`` seconds (its log at :data:`LOG_FILE` has the
    detail - most commonly an import error in a ``structure_modules`` entry, or the port already
    being used by something else).
    """
    existing = status()
    if existing is not None:
        raise ServerError(
            f"un serveur Follow API tourne déjà (pid {existing['pid']}, {existing['host']}:{existing['port']}, "
            f"dépôt {existing['repo']!r}) - arrêtez-le avec `follow_api stop` avant d'en relancer un"
        )

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    repo_path = str(Path(repo_path).resolve())

    env = dict(os.environ)
    env["FOLLOW_API_REPO"] = repo_path
    env["FOLLOW_API_HOST"] = host
    env["FOLLOW_API_PORT"] = str(port)
    env["FOLLOW_API_STRUCTURES"] = ",".join(structure_modules)

    with open(LOG_FILE, "ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "follow.api.server", "_run"],
            env=env,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=Path.cwd(),
        )

    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    META_FILE.write_text(
        json.dumps({"repo": repo_path, "host": host, "port": port, "started_at": time.time()}, indent=2),
        encoding="utf-8",
    )

    if not _wait_for_health(host, port, startup_timeout):
        # started but never became healthy - do not leave a misleading pidfile behind
        if _process_alive(process.pid):
            os.kill(process.pid, signal.SIGTERM)
        _clear_state()
        raise ServerError(
            f"le serveur n'a pas répondu sur http://{host}:{port}/api/health dans les "
            f"{startup_timeout:.0f}s - voir {LOG_FILE} pour le détail"
        )

    return status() or {"pid": process.pid, "repo": repo_path, "host": host, "port": port}


def stop(*, timeout: float = 10.0) -> bool:
    """Stop the running server (SIGTERM, then SIGKILL after ``timeout``). Returns whether a
    server was actually running to stop.
    """
    meta = status()
    if meta is None:
        return False
    pid = meta["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _clear_state()
        return True

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _process_alive(pid):
            _clear_state()
            return True
        time.sleep(0.2)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _clear_state()
    return True


def _run_from_env() -> None:
    """Entry point for the detached child process: ``python -m follow.api.server _run``."""
    import uvicorn

    from .app import create_app

    repo_path = os.environ["FOLLOW_API_REPO"]
    host = os.environ.get("FOLLOW_API_HOST", "127.0.0.1")
    port = int(os.environ.get("FOLLOW_API_PORT", "8000"))
    structures = tuple(m for m in os.environ.get("FOLLOW_API_STRUCTURES", "").split(",") if m)

    app = create_app(repo_path, structure_modules=structures)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_run":
        _run_from_env()
    else:
        print("usage: python -m follow.api.server _run", file=sys.stderr)
        sys.exit(2)
