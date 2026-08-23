"""`follow` - a git-flavoured command-line front-end for the Follow library.

An experiment is authored the same way a git commit is: `follow new`/`follow derive` write a
draft JSON file (Follow's "working tree"), you hand-edit it (add steps, evidence, a conclusion
once the experiment has run), then `follow commit` freezes it into the repository.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .graphing import render_graph_html
from .rendering import render_fiche, render_log
from .repository import ExperimentNotFoundError, Repository
from .structure import Structure

DEFAULT_REPO = ".follow"


def _repo(path: str) -> Repository:
    return Repository(Path(path))


def _fail(message: str) -> int:
    print(f"erreur: {message}", file=sys.stderr)
    return 1


def _load_structure_class(dotted: str) -> type[Structure]:
    """Import the module holding a Structure subclass so it registers itself, then return it.

    Follow only stores a dotted class path (``structure_type``) for each experiment, never the
    Python class itself, so any command that needs to validate or diff structures must import
    it on demand - exactly like Python already does for any other dynamically-named class.
    """
    if "." not in dotted:
        raise SystemExit(f"--structure-type doit être un chemin pointé, ex. pkg.module.Classe (reçu {dotted!r})")
    module_name, class_name = dotted.rsplit(".", 1)
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise SystemExit(f"impossible d'importer le module {module_name!r}: {exc}") from exc
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise SystemExit(f"{class_name!r} introuvable dans le module {module_name!r}") from exc


def _read_structure_payload(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


# -- subcommands --------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists() and any(path.iterdir()):
        return _fail(f"{path} existe déjà et n'est pas vide")
    (path / "objects").mkdir(parents=True, exist_ok=True)
    refs_file = path / "refs.json"
    if not refs_file.exists():
        refs_file.write_text(json.dumps({"branches": {}, "tags": {}}, indent=2))
    print(f"Dépôt Follow initialisé dans {path}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    structure_cls = _load_structure_class(args.structure_type)
    structure = structure_cls.model_validate(_read_structure_payload(args.structure_file))
    builder = repo.new(
        branch=args.branch,
        structure=structure,
        title=args.title,
        intent=args.intent,
        author=args.author,
        hypothesis=args.hypothesis,
    )
    out = Path(args.out)
    out.write_text(json.dumps(builder.to_draft(), indent=2, ensure_ascii=False))
    print(f"Brouillon écrit dans {out}. Éditez-le puis lancez `follow commit {out}`.")
    return 0


def cmd_derive(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    try:
        parent = repo.get(args.ref)
    except ExperimentNotFoundError as exc:
        return _fail(str(exc))

    structure_type = args.structure_type or parent.structure_type
    _load_structure_class(structure_type)

    structure = None
    if args.structure_file:
        structure = Structure.resolve(structure_type).model_validate(_read_structure_payload(args.structure_file))

    builder = repo.derive(
        parent.id,
        title=args.title,
        intent=args.intent,
        new_branch=args.new_branch,
        structure=structure,
        author=args.author,
        hypothesis=args.hypothesis,
    )
    out = Path(args.out)
    out.write_text(json.dumps(builder.to_draft(), indent=2, ensure_ascii=False))
    print(f"Brouillon dérivé de {parent.id} écrit dans {out}. Éditez-le puis lancez `follow commit {out}`.")
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    payload = _read_structure_payload(args.draft)
    try:
        _load_structure_class(payload["structure_type"])
        builder = repo.load_draft(payload)
        experiment = builder.commit()
    except (ValidationError, KeyError, ValueError) as exc:
        return _fail(str(exc))
    print(f"{experiment.id}  ({experiment.branch})  {experiment.title}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    try:
        history = repo.log(args.ref)
    except ExperimentNotFoundError as exc:
        return _fail(str(exc))
    for exp in history[: args.number]:
        print(f"{exp.id}  ({exp.branch})  {exp.title}  [{exp.conclusion.status}]")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    try:
        experiment = repo.get(args.ref)
    except ExperimentNotFoundError as exc:
        return _fail(str(exc))
    _load_structure_class(experiment.structure_type)
    for reference in experiment.references:
        if reference.role == "baseline" and reference.experiment_id and reference.experiment_id in repo:
            _load_structure_class(repo.get(reference.experiment_id).structure_type)
    print(render_fiche(experiment, repo))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    try:
        a, b = repo.get(args.ref_a), repo.get(args.ref_b)
    except ExperimentNotFoundError as exc:
        return _fail(str(exc))
    _load_structure_class(a.structure_type)
    _load_structure_class(b.structure_type)
    diff = repo.diff(args.ref_a, args.ref_b)
    if not diff:
        print("(aucune différence)")
        return 0
    for entry in diff:
        print(entry)
    return 0


def cmd_branch(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    if args.name is None:
        for name, exp_id in sorted(repo.branches.items()):
            print(f"  {name:24s} {exp_id}")
        return 0
    if args.at is None:
        return _fail("--at <ref> est requis pour créer/déplacer une branche")
    try:
        repo.branch(args.name, args.at)
    except ExperimentNotFoundError as exc:
        return _fail(str(exc))
    print(f"branche '{args.name}' -> {repo.get(args.name).id}")
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    if args.name is None:
        for name, exp_id in sorted(repo.tags.items()):
            print(f"  {name:24s} {exp_id}")
        return 0
    if args.at is None:
        return _fail("--at <ref> est requis pour créer un tag")
    try:
        repo.tag(args.name, args.at)
    except ExperimentNotFoundError as exc:
        return _fail(str(exc))
    print(f"tag '{args.name}' -> {repo.get(args.name).id}")
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    out = render_graph_html(repo, args.out)
    print(f"Graphe écrit dans {out}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


# -- argument parsing --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="follow", description="Suivi façon git pour les expériences scientifiques.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_repo_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo", default=DEFAULT_REPO, help=f"chemin du dépôt (défaut: {DEFAULT_REPO})")

    p_init = subparsers.add_parser("init", help="créer un nouveau dépôt")
    p_init.add_argument("path", nargs="?", default=DEFAULT_REPO)
    p_init.set_defaults(func=cmd_init)

    p_new = subparsers.add_parser("new", help="démarrer un brouillon d'expérience racine (sans parent)")
    add_repo_arg(p_new)
    p_new.add_argument("--branch", required=True)
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--intent", required=True)
    p_new.add_argument("--structure-type", required=True, help="chemin pointé, ex. examples.recipe.CakeRecipe")
    p_new.add_argument("--structure-file", required=True, help="fichier JSON conforme au type de structure")
    p_new.add_argument("--author")
    p_new.add_argument("--hypothesis")
    p_new.add_argument("--out", default="draft.json")
    p_new.set_defaults(func=cmd_new)

    p_derive = subparsers.add_parser("derive", help="dériver un brouillon depuis une expérience existante")
    add_repo_arg(p_derive)
    p_derive.add_argument("ref", help="id, branche ou tag de l'expérience parente")
    p_derive.add_argument("--title", required=True)
    p_derive.add_argument("--intent", required=True)
    p_derive.add_argument("--new-branch", help="créer/utiliser cette branche au lieu de continuer celle du parent")
    p_derive.add_argument("--structure-type", help="remplace le type hérité du parent")
    p_derive.add_argument("--structure-file", help="remplace la structure héritée du parent")
    p_derive.add_argument("--author")
    p_derive.add_argument("--hypothesis")
    p_derive.add_argument("--out", default="draft.json")
    p_derive.set_defaults(func=cmd_derive)

    p_commit = subparsers.add_parser("commit", help="figer un brouillon dans le dépôt")
    add_repo_arg(p_commit)
    p_commit.add_argument("draft", help="fichier JSON produit par `new`/`derive` (ou édité à la main)")
    p_commit.set_defaults(func=cmd_commit)

    p_log = subparsers.add_parser("log", help="historique d'une branche/tag/expérience")
    add_repo_arg(p_log)
    p_log.add_argument("ref", nargs="?", default="main")
    p_log.add_argument("-n", "--number", type=int, default=10**9)
    p_log.set_defaults(func=cmd_log)

    p_show = subparsers.add_parser("show", help="afficher la fiche d'une expérience")
    add_repo_arg(p_show)
    p_show.add_argument("ref")
    p_show.set_defaults(func=cmd_show)

    p_diff = subparsers.add_parser("diff", help="diff structurel entre deux expériences")
    add_repo_arg(p_diff)
    p_diff.add_argument("ref_a")
    p_diff.add_argument("ref_b")
    p_diff.set_defaults(func=cmd_diff)

    p_branch = subparsers.add_parser("branch", help="lister ou créer/déplacer une branche")
    add_repo_arg(p_branch)
    p_branch.add_argument("name", nargs="?")
    p_branch.add_argument("--at", help="id/branche/tag à pointer")
    p_branch.set_defaults(func=cmd_branch)

    p_tag = subparsers.add_parser("tag", help="lister ou créer un tag")
    add_repo_arg(p_tag)
    p_tag.add_argument("name", nargs="?")
    p_tag.add_argument("--at", help="id/branche/tag à pointer")
    p_tag.set_defaults(func=cmd_tag)

    p_graph = subparsers.add_parser("graph", help="exporter le graphe de filiation (HTML Plotly)")
    add_repo_arg(p_graph)
    p_graph.add_argument("--out", default="graph.html")
    p_graph.add_argument("--open", action="store_true", help="ouvrir le fichier dans le navigateur")
    p_graph.set_defaults(func=cmd_graph)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
