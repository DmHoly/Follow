"""`follow_api` - start/stop/status for the Follow API + GUI server (see :mod:`follow.api.server`)."""

from __future__ import annotations

import argparse
import sys

from .server import LOG_FILE, ServerError, start, status, stop

DEFAULT_REPO = ".follow"


def _fail(message: str) -> int:
    print(f"erreur: {message}", file=sys.stderr)
    return 1


def cmd_start(args: argparse.Namespace) -> int:
    structures = tuple(m for entry in args.structures for m in entry.split(",") if m)
    try:
        meta = start(
            args.repo,
            host=args.host,
            port=args.port,
            structure_modules=structures,
            startup_timeout=args.timeout,
        )
    except ServerError as exc:
        return _fail(str(exc))
    print(f"Follow API démarrée (pid {meta['pid']}) sur http://{meta['host']}:{meta['port']} — dépôt {meta['repo']}")
    print(f"Interface web : http://{meta['host']}:{meta['port']}/")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    stopped = stop(timeout=args.timeout)
    if not stopped:
        print("Aucun serveur Follow API en cours d'exécution.")
        return 0
    print("Follow API arrêtée.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    meta = status()
    if meta is None:
        print("Aucun serveur Follow API en cours d'exécution.")
        return 1
    print(f"Follow API en cours (pid {meta['pid']}) sur http://{meta['host']}:{meta['port']} — dépôt {meta['repo']}")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    print(LOG_FILE)
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    stop(timeout=args.timeout)
    return cmd_start(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="follow_api", description="Serveur API + interface web pour Follow.")
    sub = parser.add_subparsers(dest="command", required=True)

    start_p = sub.add_parser("start", help="démarrer le serveur en arrière-plan")
    start_p.add_argument("--repo", default=DEFAULT_REPO, help=f"chemin du dépôt Follow (défaut: {DEFAULT_REPO})")
    start_p.add_argument("--host", default="127.0.0.1")
    start_p.add_argument("--port", type=int, default=8000)
    start_p.add_argument(
        "--structures",
        action="append",
        default=[],
        metavar="module.path",
        help="module(s) Python à importer pour enregistrer des types de Structure "
        "supplémentaires (répétable, ou séparés par des virgules)",
    )
    start_p.add_argument("--timeout", type=float, default=10.0, help="secondes à attendre que le serveur réponde")
    start_p.set_defaults(func=cmd_start)

    stop_p = sub.add_parser("stop", help="arrêter le serveur en arrière-plan")
    stop_p.add_argument("--timeout", type=float, default=10.0, help="secondes avant un arrêt forcé (SIGKILL)")
    stop_p.set_defaults(func=cmd_stop)

    status_p = sub.add_parser("status", help="afficher l'état du serveur")
    status_p.set_defaults(func=cmd_status)

    restart_p = sub.add_parser("restart", help="arrêter puis redémarrer le serveur")
    restart_p.add_argument("--repo", default=DEFAULT_REPO)
    restart_p.add_argument("--host", default="127.0.0.1")
    restart_p.add_argument("--port", type=int, default=8000)
    restart_p.add_argument("--structures", action="append", default=[], metavar="module.path")
    restart_p.add_argument("--timeout", type=float, default=10.0)
    restart_p.set_defaults(func=cmd_restart)

    log_p = sub.add_parser("logs", help="afficher le chemin du fichier de log du serveur")
    log_p.set_defaults(func=cmd_logs)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
