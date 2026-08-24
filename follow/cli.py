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

from . import __version__
from .batch import analyze_batch
from .entities import find_entity_mentions
from .formatting import format_value
from .graphing import render_graph_html
from .rendering import render_fiche, render_log
from .report import batch_table, escape_html, render_page, render_study_html
from .repository import FollowError, Repository
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
    """Read and parse a JSON file (a ``--structure-file`` or a draft passed to ``commit``),
    turning the common mistakes - a typo'd path, a directory, unreadable permissions, or
    hand-edited JSON with a syntax error - into a clean one-line message instead of a traceback.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"fichier introuvable : {path}") from exc
    except IsADirectoryError as exc:
        raise SystemExit(f"{path} est un dossier, pas un fichier") from exc
    except PermissionError as exc:
        raise SystemExit(f"permission refusée pour lire {path}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} n'est pas un JSON valide : {exc}") from exc


def _print_form_hint(repo: Repository) -> None:
    """After writing a draft, tell the user up front which form fields `commit` will require -
    otherwise the first they'd hear of the repository's commit form is a refusal at commit time.
    """
    if repo.commit_form is None:
        return
    print(f"Ce dépôt exige un formulaire de commit ({repo.commit_form.title!r}) :")
    for field in repo.commit_form.fields:
        marker = "requis" if field.required else "optionnel"
        print(f"  - {field.name} ({field.type}, {marker}): {field.label}")
    print('Remplissez "form_answers" dans le brouillon avant de committer.')


def _write_draft(out: Path, builder: Any, *, force: bool) -> int | None:
    """Write a builder's draft JSON to ``out``, refusing to clobber an existing file unless
    ``force`` is set - re-running ``new``/``derive``/``merge`` with the same ``--out`` (e.g. by
    mistake, or a retried script) would otherwise silently overwrite hand-edited work in
    progress with no way to get it back.
    """
    if out.exists() and not force:
        return _fail(f"{out} existe déjà - passez --force pour l'écraser, ou choisissez un autre --out")
    # ensure_ascii=False keeps accented titles readable in the draft, so the encoding has to
    # be pinned: the platform default would mangle them on a non-UTF-8 locale
    out.write_text(json.dumps(builder.to_draft(), indent=2, ensure_ascii=False), encoding="utf-8")
    return None


# -- subcommands --------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists() and not path.is_dir():
        return _fail(f"{path} existe déjà et n'est pas un dossier")
    if path.exists() and any(path.iterdir()):
        return _fail(f"{path} existe déjà et n'est pas vide")
    (path / "objects").mkdir(parents=True, exist_ok=True)
    refs_file = path / "refs.json"
    if not refs_file.exists():
        refs_file.write_text(json.dumps({"branches": {}, "tags": {}}, indent=2), encoding="utf-8")
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
    if (failure := _write_draft(out, builder, force=args.force)) is not None:
        return failure
    print(f"Brouillon écrit dans {out}. Éditez-le puis lancez `follow commit {out}`.")
    _print_form_hint(repo)
    return 0


def cmd_derive(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    try:
        parent = repo.get(args.ref)
    except FollowError as exc:
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
    if (failure := _write_draft(out, builder, force=args.force)) is not None:
        return failure
    print(f"Brouillon dérivé de {parent.id} écrit dans {out}. Éditez-le puis lancez `follow commit {out}`.")
    _print_form_hint(repo)
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    payload = _read_structure_payload(args.draft)
    try:
        _load_structure_class(payload["structure_type"])
        builder = repo.load_draft(payload)
        experiment = builder.commit()
    except (ValidationError, FollowError, KeyError, ValueError) as exc:
        return _fail(str(exc))
    print(f"{experiment.id}  ({experiment.branch})  {experiment.title}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    if args.number < 0:
        return _fail("-n/--number doit être positif")
    repo = _repo(args.repo)
    try:
        history = repo.log(args.ref)
    except FollowError as exc:
        return _fail(str(exc))
    for exp in history[: args.number]:
        print(f"{exp.id}  ({exp.branch})  {exp.title}  [{exp.conclusion.status}]")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    try:
        experiment = repo.get(args.ref)
    except FollowError as exc:
        return _fail(str(exc))
    _load_structure_class(experiment.structure_type)
    for reference in experiment.references:
        if reference.role == "baseline" and reference.experiment_id and reference.experiment_id in repo:
            _load_structure_class(repo.get(reference.experiment_id).structure_type)
    print(render_fiche(experiment, repo))
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    matches = repo.find_entity(args.entity_id)
    if not matches:
        print(f"aucune expérience ne mentionne l'entité {args.entity_id!r}")
        return 0
    for exp in matches:
        paths = find_entity_mentions(exp.structure, args.entity_id)
        where = ", ".join(p or "(racine)" for p in paths)
        print(f"{exp.id}  ({exp.branch})  {exp.title}  [{exp.conclusion.status}]  -- {where}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    try:
        a, b = repo.get(args.ref_a), repo.get(args.ref_b)
    except FollowError as exc:
        return _fail(str(exc))
    if args.steps:
        diff = repo.diff_steps(args.ref_a, args.ref_b)
    else:
        _load_structure_class(a.structure_type)
        _load_structure_class(b.structure_type)
        diff = repo.diff(args.ref_a, args.ref_b)
    if not diff:
        print("(aucune différence)")
        return 0
    for entry in diff:
        print(entry)
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    try:
        a, b = repo.get(args.ref_a), repo.get(args.ref_b)
    except FollowError as exc:
        return _fail(str(exc))
    _load_structure_class(a.structure_type)
    _load_structure_class(b.structure_type)
    try:
        builder = repo.merge(
            a.id,
            b.id,
            title=args.title,
            intent=args.intent,
            take_structure=args.take_structure,
            take_steps=args.take_steps,
            branch=args.branch,
            author=args.author,
            hypothesis=args.hypothesis,
        )
    except (FollowError, ValueError, KeyError, IndexError, TypeError) as exc:
        return _fail(str(exc))
    out = Path(args.out)
    if (failure := _write_draft(out, builder, force=args.force)) is not None:
        return failure
    print(f"Brouillon de fusion ({a.id} + {b.id}) écrit dans {out}. Éditez-le puis lancez `follow commit {out}`.")
    _print_form_hint(repo)
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
        repo.branch(args.name, args.at, force=args.force)
    except FollowError as exc:
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
        repo.tag(args.name, args.at, force=args.force)
    except FollowError as exc:
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


def cmd_explode(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    try:
        experiment = repo.get(args.ref)
    except FollowError as exc:
        return _fail(str(exc))
    _load_structure_class(experiment.structure_type)
    structure = repo.load_structure(experiment)

    entities: Any = structure
    for part in args.path.split("."):
        try:
            entities = getattr(entities, part)
        except AttributeError:
            return _fail(f"{args.path!r} n'existe pas sur la structure de {experiment.id}")
    if not isinstance(entities, list):
        return _fail(f"{args.path!r} n'est pas une liste d'entités (type: {type(entities).__name__})")

    try:
        variation = analyze_batch(entities, ignore=args.ignore)
    except (KeyError, IndexError, TypeError) as exc:
        return _fail(f"entités hétérogènes dans {args.path!r}: {exc}")

    if args.out is not None:
        # the experiment's own title is repository data, not a literal this command controls:
        # render_page inserts heading/subtitle as raw HTML, so it is escaped here before it gets
        # there (title/description are escaped by render_page itself, being attribute/text slots)
        page_title = f"{experiment.title} — {args.path}"
        section = batch_table(variation, title=page_title)
        html = render_page(
            title=page_title,
            description=f"Vue explosée de {args.path!r} pour l'expérience {experiment.id}.",
            eyebrow="Follow · vue explosée",
            heading=escape_html(page_title),
            subtitle=f"{variation.entity_count} entités, {len(variation.varying)} paramètre(s) variable(s).",
            stat_chips=[f"<b>{variation.entity_count}</b> entités", f"<b>{len(variation.varying)}</b> variables"],
            sections=[f'  <section class="section">\n{section}\n  </section>'],
            footer="",
        )
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Vue explosée écrite dans {out}")
        if args.open:
            webbrowser.open(out.resolve().as_uri())
        return 0

    print(f"{variation.entity_count} entités  ·  {len(variation.constant)} constant(s)  ·  {len(variation.varying)} variable(s)")
    if variation.constant:
        print("\nconstants:")
        for path, value in variation.constant.items():
            print(f"  {path}: {format_value(value)}")
    if variation.varying:
        print("\nvariables:")
        for factor in variation.varying:
            values = ", ".join(format_value(v) for v in factor.values)
            print(f"  {factor.path}: [{values}]")
    else:
        print("\n(aucune variation - toutes les entités sont identiques)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    if args.ref is not None and args.ref not in repo:
        return _fail(f"No experiment, branch or tag matches {args.ref!r}")
    for exp in repo:
        _load_structure_class(exp.structure_type)
    html = render_study_html(
        repo, ref=args.ref, title=args.title, description=args.description or "", embed_plotly=not args.no_embed
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Rapport écrit dans {out}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_menu(args: argparse.Namespace) -> int:
    from .menu import run_menu  # optional dependency (questionary) - only needed for this command

    return run_menu(args.repo)


# -- argument parsing --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="follow", description="Suivi façon git pour les expériences scientifiques.")
    parser.add_argument("--version", action="version", version=f"follow {__version__}")
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
    p_new.add_argument("--force", action="store_true", help="écraser --out s'il existe déjà")
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
    p_derive.add_argument("--force", action="store_true", help="écraser --out s'il existe déjà")
    p_derive.set_defaults(func=cmd_derive)

    p_merge = subparsers.add_parser("merge", help="fusionner deux lignes de travail (git merge)")
    add_repo_arg(p_merge)
    p_merge.add_argument("ref_a", help="cible de la fusion, ex. la branche principale")
    p_merge.add_argument("ref_b", help="ligne à fusionner dedans, ex. la branche de test")
    p_merge.add_argument("--title", required=True)
    p_merge.add_argument("--intent", required=True)
    p_merge.add_argument("--branch", help="branche du commit de fusion (défaut: celle de ref_a)")
    p_merge.add_argument(
        "--take-structure",
        action="append",
        default=[],
        dest="take_structure",
        metavar="PATH",
        help="chemin de structure (voir `follow diff`) à prendre depuis ref_b plutôt que ref_a; répétable",
    )
    p_merge.add_argument(
        "--take-steps",
        action="append",
        default=[],
        dest="take_steps",
        metavar="PATH",
        help="chemin d'étape (voir `follow diff --steps`) à prendre depuis ref_b plutôt que ref_a; répétable",
    )
    p_merge.add_argument("--author")
    p_merge.add_argument("--hypothesis")
    p_merge.add_argument("--out", default="draft.json")
    p_merge.add_argument("--force", action="store_true", help="écraser --out s'il existe déjà")
    p_merge.set_defaults(func=cmd_merge)

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

    p_trace = subparsers.add_parser(
        "trace",
        help="retrouver toutes les expériences qui mentionnent une même entité physique (entity_id), tous branches et lignages confondus",
    )
    add_repo_arg(p_trace)
    p_trace.add_argument("entity_id", help="nom donné à l'entité physique, ex. moule-vert")
    p_trace.set_defaults(func=cmd_trace)

    p_diff = subparsers.add_parser("diff", help="diff structurel (ou de protocole) entre deux expériences")
    add_repo_arg(p_diff)
    p_diff.add_argument("ref_a")
    p_diff.add_argument("ref_b")
    p_diff.add_argument("--steps", action="store_true", help="comparer les étapes du protocole plutôt que la structure")
    p_diff.set_defaults(func=cmd_diff)

    p_branch = subparsers.add_parser("branch", help="lister ou créer/déplacer une branche")
    add_repo_arg(p_branch)
    p_branch.add_argument("name", nargs="?")
    p_branch.add_argument("--at", help="id/branche/tag à pointer")
    p_branch.add_argument(
        "--force",
        action="store_true",
        help="déplacer une branche existante vers un commit dont sa pointe ne descend pas (abandonne cet historique)",
    )
    p_branch.set_defaults(func=cmd_branch)

    p_tag = subparsers.add_parser("tag", help="lister ou créer un tag")
    add_repo_arg(p_tag)
    p_tag.add_argument("name", nargs="?")
    p_tag.add_argument("--at", help="id/branche/tag à pointer")
    p_tag.add_argument("--force", action="store_true", help="repointer un tag existant (les tags sont immuables par défaut)")
    p_tag.set_defaults(func=cmd_tag)

    p_graph = subparsers.add_parser("graph", help="exporter le graphe de filiation (HTML Plotly)")
    add_repo_arg(p_graph)
    p_graph.add_argument("--out", default="graph.html")
    p_graph.add_argument("--open", action="store_true", help="ouvrir le fichier dans le navigateur")
    p_graph.set_defaults(func=cmd_graph)

    p_explode = subparsers.add_parser(
        "explode",
        help="éclater une liste d'entités d'une expérience (DOE) en baseline constante + facteurs variables",
    )
    add_repo_arg(p_explode)
    p_explode.add_argument("ref", help="id, branche ou tag de l'expérience")
    p_explode.add_argument("path", help="champ liste de la structure à éclater, ex. wafers")
    p_explode.add_argument(
        "--ignore", action="append", default=[], metavar="FIELD",
        help="champ d'identité à exclure de la comparaison (ex. un numéro de slot); répétable",
    )
    p_explode.add_argument("--out", help="écrire une page HTML au lieu d'afficher un résumé texte")
    p_explode.add_argument("--open", action="store_true", help="ouvrir le fichier HTML dans le navigateur (avec --out)")
    p_explode.set_defaults(func=cmd_explode)

    p_report = subparsers.add_parser(
        "report", help="générer un compte rendu d'étude complet (HTML, sans IA, dérivé du dépôt)"
    )
    add_repo_arg(p_report)
    p_report.add_argument("ref", nargs="?", default=None, help="limiter au lignage d'une branche/tag/expérience (défaut: tout le dépôt)")
    p_report.add_argument("--title", default="Compte rendu d'étude")
    p_report.add_argument("--description")
    p_report.add_argument("--out", default="report.html")
    p_report.add_argument("--no-embed", action="store_true", help="utiliser le CDN Plotly au lieu de l'inclure (fichier plus léger)")
    p_report.add_argument("--open", action="store_true", help="ouvrir le fichier dans le navigateur")
    p_report.set_defaults(func=cmd_report)

    p_menu = subparsers.add_parser(
        "menu", help="menu interactif (naviguer, lancer, suivre, clôturer une expérience) — nécessite `questionary`"
    )
    add_repo_arg(p_menu)
    p_menu.set_defaults(func=cmd_menu)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
