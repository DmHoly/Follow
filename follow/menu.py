"""An interactive, menu-driven front-end for the CLI (``follow menu``): navigate experiments,
start one, follow its history, close it out, merge, report - without memorizing subcommands and
flags. This wraps the exact same :class:`~follow.repository.Repository`/
:class:`~follow.repository.ExperimentBuilder` API the scriptable ``new``/``derive``/``commit``/
``merge`` subcommands use (see :mod:`follow.cli`) - nothing here is a second implementation of
the engine, just a friendlier way to drive it. The scriptable subcommands are unaffected and
remain the way to drive Follow from scripts/CI.

Optional: requires ``questionary`` (``pip install "follow[menu]"``). The rest of the CLI works
without it - this module is only imported when ``follow menu`` actually runs.

Structure authoring is deliberately **not** reinvented here: like ``follow new --structure-file``,
you still point at a JSON file for the ``Structure`` itself (arbitrary Pydantic shapes aren't
something a generic prompt wizard can build safely). What the menu adds interactive prompts for
is the parts with a fixed, known shape - objectives, evidence, conclusion - and for navigation:
picking an experiment, a branch, or which diff paths to take in a merge, from an actual list
instead of copying ids by hand.

Every :func:`questionary.confirm` call below passes ``auto_enter=False`` - with the default
``auto_enter=True``, confirm resolves the instant ``y``/``n`` is pressed and never reads the
Enter keystroke that follows it out of habit (typing "y" then Enter is how confirmations work in
most other CLIs); that stray Enter is left sitting in the terminal's input buffer and gets
delivered to whatever prompt comes next, silently submitting it (an empty string for a text
prompt, the highlighted item for a select) as if the user had answered without ever seeing it.
``auto_enter=False`` makes confirm consume the Enter itself instead of leaking it forward.
"""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any, Callable

from .cli import DEFAULT_REPO, _load_structure_class, _print_form_hint, _read_structure_payload, _repo
from .diffing import DiffEntry
from .graphing import render_graph_html
from .models import Experiment
from .quantity import Quantity
from .rendering import render_fiche
from .report import render_study_html
from .repository import ExperimentBuilder, FollowError, Repository

try:
    import questionary
except ImportError:  # pragma: no cover - exercised via _require_questionary()
    questionary = None


def _require_questionary() -> None:
    if questionary is None:
        raise SystemExit('follow menu nécessite `questionary` : pip install "follow[menu]" (ou `pip install questionary`)')


def _fmt(exp: Experiment) -> str:
    decision = f" · {exp.conclusion.decision}" if exp.conclusion.decision else ""
    return f"{exp.id[:12]}  {exp.branch:<20}  {exp.title}  [{exp.conclusion.status}{decision}]"


def _fmt_diff(entry: DiffEntry) -> str:
    return f"{entry.path}: {entry.before!r} -> {entry.after!r}"


def _pick_experiment(repo: Repository, message: str = "Quelle expérience ?") -> Experiment | None:
    experiments = sorted(repo, key=lambda e: e.created_at, reverse=True)
    if not experiments:
        questionary.print("Aucune expérience dans ce dépôt.", style="fg:yellow")
        return None
    choice = questionary.select(message, choices=[questionary.Choice(_fmt(e), value=e.id) for e in experiments]).ask()
    return repo.get(choice) if choice else None


def _collect_objectives(builder: ExperimentBuilder) -> None:
    while questionary.confirm("Ajouter un objectif ?", default=False, auto_enter=False).ask():
        name = questionary.text("Nom de l'objectif :").ask()
        if not name:
            break
        metric = questionary.text("Métrique (clé utilisée dans evidence/observed) :").ask() or name
        direction = questionary.select(
            "Direction :", choices=["maximize", "minimize", "target", "range", "observe"]
        ).ask()
        kwargs: dict[str, Any] = {"name": name, "metric": metric, "direction": direction}
        if direction == "range":
            low = questionary.text("Plage - borne basse :").ask()
            high = questionary.text("Plage - borne haute :").ask()
            if low and high:
                kwargs["range"] = (float(low), float(high))
        else:
            target = questionary.text("Cible (nombre, vide pour aucune) :").ask()
            if target:
                kwargs["target"] = float(target)
        rationale = questionary.text("Justification (optionnel) :").ask()
        if rationale:
            kwargs["rationale"] = rationale
        builder.add_objective(**kwargs)


def _collect_evidence(builder: ExperimentBuilder) -> None:
    while questionary.confirm("Ajouter une preuve ?", default=False, auto_enter=False).ask():
        eid = questionary.text("Identifiant de la preuve :").ask()
        if not eid:
            break
        description = questionary.text("Description :").ask() or ""
        source = questionary.text("Source (chemin, URL, notebook:///...) :").ask() or ""
        builder.add_evidence(id=eid, description=description, source=source)


def _collect_conclusion(builder: ExperimentBuilder) -> None:
    if not questionary.confirm("Conclure maintenant ?", default=False, auto_enter=False).ask():
        return
    status = questionary.select("Statut :", choices=["concluded", "running", "abandoned"]).ask()
    decision = questionary.select(
        "Décision :", choices=["(aucune)", "promote", "branch", "replicate", "abandon", "inconclusive"]
    ).ask()
    summary = questionary.text("Résumé :").ask()
    next_steps = questionary.text("Suite (optionnel) :").ask()
    kwargs: dict[str, Any] = {"status": status}
    if decision and decision != "(aucune)":
        kwargs["decision"] = decision
    if summary:
        kwargs["summary"] = summary
    if next_steps:
        kwargs["next_steps"] = next_steps

    objective_results = []
    for objective in builder.objectives:
        if not questionary.confirm(f"Résultat pour l'objectif {objective.name!r} ?", default=True, auto_enter=False).ask():
            continue
        obj_status = questionary.select("Verdict :", choices=["met", "not_met", "partially_met", "inconclusive"]).ask()
        observed_value = questionary.text(f"Valeur observée pour {objective.metric!r} (nombre, optionnel) :").ask()
        observed_unit = questionary.text("Unité (optionnel) :").ask() if observed_value else None
        reasoning = questionary.text("Raisonnement (optionnel) :").ask()
        result: dict[str, Any] = {"objective": objective.name, "status": obj_status}
        if observed_value:
            result["observed"] = Quantity(value=float(observed_value), unit=observed_unit or None)
        if reasoning:
            result["reasoning"] = reasoning
        evidence_ids = [e.id for e in builder.evidence]
        if evidence_ids:
            chosen = questionary.checkbox(f"Preuve(s) citée(s) pour {objective.name!r} :", choices=evidence_ids).ask()
            if chosen:
                result["evidence_ids"] = chosen
        objective_results.append(result)
    if objective_results:
        kwargs["objective_results"] = objective_results

    builder.conclude(**kwargs)


def _collect_form_answers(repo: Repository, builder: ExperimentBuilder) -> None:
    """Prompt for the repository's commit form (see :mod:`follow.commit_form`), if one is
    configured - skipped entirely for a repository with none. Without this, a repo with a
    mandatory commit form would always reject the commit :func:`_finish` tries to make, with no
    way to have answered it first.
    """
    if repo.commit_form is None:
        return
    questionary.print(f"Formulaire de commit requis : {repo.commit_form.title!r}", style="bold")
    for field in repo.commit_form.fields:
        current = builder.form_answers.get(field.name)
        label = f"{field.label} ({'requis' if field.required else 'optionnel'})"
        if field.type == "boolean":
            value = questionary.confirm(label, default=bool(current), auto_enter=False).ask()
        elif field.type == "choice":
            default_choice = current if current in (field.choices or []) else None
            value = questionary.select(label, choices=field.choices or [], default=default_choice).ask()
        elif field.type == "number":
            raw = questionary.text(label, default=str(current) if current is not None else "").ask()
            value = float(raw) if raw else None
        else:  # string / text
            value = questionary.text(label, default=str(current) if current else "").ask()
        if value not in (None, ""):
            builder.answer_form(**{field.name: value})


def _finish(repo: Repository, builder: ExperimentBuilder, *, default_out: str = "draft.json") -> None:
    _collect_form_answers(repo, builder)
    if questionary.confirm("Committer maintenant ?", default=True, auto_enter=False).ask():
        experiment = builder.commit()
        questionary.print(f"Committé : {experiment.id}  ({experiment.branch})  {experiment.title}", style="bold fg:green")
        return
    out = questionary.path("Fichier de brouillon :", default=default_out).ask() or default_out
    out_path = Path(out)
    if out_path.exists() and not questionary.confirm(f"{out_path} existe déjà, écraser ?", default=False, auto_enter=False).ask():
        questionary.print("Annulé.", style="fg:yellow")
        return
    out_path.write_text(json.dumps(builder.to_draft(), indent=2, ensure_ascii=False), encoding="utf-8")
    questionary.print(f"Brouillon écrit dans {out_path}.", style="fg:green")
    _print_form_hint(repo)


def _action_list(repo: Repository) -> None:
    if not repo.branches:
        questionary.print("Dépôt vide.", style="fg:yellow")
        return
    questionary.print("Branches :", style="bold")
    for name, exp_id in sorted(repo.branches.items()):
        questionary.print(f"  {name:<20} {_fmt(repo.get(exp_id))}")
    if repo.tags:
        questionary.print("\nTags :", style="bold")
        for name, exp_id in sorted(repo.tags.items()):
            questionary.print(f"  {name:<20} -> {exp_id[:12]}")


def _action_show(repo: Repository) -> None:
    exp = _pick_experiment(repo)
    if exp is None:
        return
    _load_structure_class(exp.structure_type)
    for reference in exp.references:
        if reference.role == "baseline" and reference.experiment_id and reference.experiment_id in repo:
            _load_structure_class(repo.get(reference.experiment_id).structure_type)
    questionary.print(render_fiche(exp, repo))


def _action_new(repo: Repository) -> None:
    branch = questionary.text("Branche :", default="main").ask()
    if not branch:
        return
    title = questionary.text("Titre :").ask()
    intent = questionary.text("Intention :").ask()
    if not title or not intent:
        questionary.print("Titre et intention sont requis.", style="fg:red")
        return
    hypothesis = questionary.text("Hypothèse (optionnel) :").ask()
    structure_type = questionary.text("Type de structure (module.Classe) :").ask()
    if not structure_type:
        return
    structure_cls = _load_structure_class(structure_type)
    structure_file = questionary.path("Fichier JSON de structure :").ask()
    if not structure_file:
        return
    structure = structure_cls.model_validate(_read_structure_payload(structure_file))

    builder = repo.new(branch=branch, structure=structure, title=title, intent=intent, hypothesis=hypothesis or None)
    _collect_objectives(builder)
    _collect_evidence(builder)
    _collect_conclusion(builder)
    _finish(repo, builder)


def _action_derive(repo: Repository) -> None:
    parent = _pick_experiment(repo, "Dériver depuis quelle expérience ?")
    if parent is None:
        return
    title = questionary.text("Titre :").ask()
    intent = questionary.text("Intention :").ask()
    if not title or not intent:
        questionary.print("Titre et intention sont requis.", style="fg:red")
        return
    new_branch = questionary.text("Nouvelle branche (vide pour continuer celle du parent) :").ask()
    structure_cls = _load_structure_class(parent.structure_type)
    structure = None
    if questionary.confirm("Remplacer la structure héritée par un nouveau fichier JSON ?", default=False, auto_enter=False).ask():
        structure_file = questionary.path("Fichier JSON de structure :").ask()
        if structure_file:
            structure = structure_cls.model_validate(_read_structure_payload(structure_file))
    builder = repo.derive(parent.id, title=title, intent=intent, new_branch=new_branch or None, structure=structure)
    _collect_objectives(builder)
    _collect_evidence(builder)
    _collect_conclusion(builder)
    _finish(repo, builder)


def _action_close_draft(repo: Repository) -> None:
    path = questionary.path("Fichier de brouillon à clôturer :", default="draft.json").ask()
    if not path:
        return
    payload = _read_structure_payload(path)
    _load_structure_class(payload["structure_type"])
    builder = repo.load_draft(payload)
    if builder.conclusion.status == "draft":
        questionary.print("Ce brouillon n'a pas encore de conclusion.", style="fg:yellow")
        _collect_conclusion(builder)
    _collect_form_answers(repo, builder)
    experiment = builder.commit()
    questionary.print(f"Committé : {experiment.id}  ({experiment.branch})  {experiment.title}", style="bold fg:green")


def _action_merge(repo: Repository) -> None:
    if len(repo.branches) < 2:
        questionary.print("Il faut au moins deux branches pour fusionner.", style="fg:yellow")
        return
    branch_names = sorted(repo.branches)
    ref_a = questionary.select("Fusionner DANS quelle branche ?", choices=branch_names).ask()
    if not ref_a:
        return
    ref_b = questionary.select("Fusionner QUELLE branche ?", choices=[b for b in branch_names if b != ref_a]).ask()
    if not ref_b:
        return
    a, b = repo.get(ref_a), repo.get(ref_b)
    _load_structure_class(a.structure_type)
    _load_structure_class(b.structure_type)

    take_structure: list[str] = []
    struct_diff = repo.diff(ref_a, ref_b)
    if struct_diff:
        take_structure = questionary.checkbox(
            f"Quels chemins de structure prendre depuis {ref_b!r} (plutôt que {ref_a!r}) ?",
            choices=[questionary.Choice(_fmt_diff(entry), value=entry.path) for entry in struct_diff],
        ).ask() or []

    take_steps: list[str] = []
    steps_diff = repo.diff_steps(ref_a, ref_b)
    if steps_diff:
        take_steps = questionary.checkbox(
            f"Quels chemins d'étape prendre depuis {ref_b!r} ?",
            choices=[questionary.Choice(_fmt_diff(entry), value=entry.path) for entry in steps_diff],
        ).ask() or []

    title = questionary.text("Titre de la fusion :").ask()
    intent = questionary.text("Intention :").ask()
    if not title or not intent:
        questionary.print("Titre et intention sont requis.", style="fg:red")
        return
    builder = repo.merge(ref_a, ref_b, title=title, intent=intent, take_structure=take_structure, take_steps=take_steps)
    _collect_conclusion(builder)
    _finish(repo, builder)


def _action_report(repo: Repository) -> None:
    out = questionary.path("Fichier de sortie :", default="report.html").ask()
    if not out:
        return
    for exp in repo:
        _load_structure_class(exp.structure_type)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_study_html(repo), encoding="utf-8")
    questionary.print(f"Rapport écrit dans {out_path}.", style="fg:green")
    if questionary.confirm("Ouvrir dans le navigateur ?", default=True, auto_enter=False).ask():
        webbrowser.open(out_path.resolve().as_uri())


def _action_graph(repo: Repository) -> None:
    out = questionary.path("Fichier de sortie :", default="graph.html").ask()
    if not out:
        return
    out_path = render_graph_html(repo, Path(out))
    questionary.print(f"Graphe écrit dans {out_path}.", style="fg:green")
    if questionary.confirm("Ouvrir dans le navigateur ?", default=True, auto_enter=False).ask():
        webbrowser.open(out_path.resolve().as_uri())


# label -> action, in menu order. A plain module-level list (not a dict) so the order shown is
# the order declared here, and so two actions could share a label if that ever made sense.
_ACTIONS: list[tuple[str, Callable[[Repository], None]]] = [
    ("Lister les branches et tags", _action_list),
    ("Voir la fiche d'une expérience", _action_show),
    ("Démarrer une nouvelle expérience", _action_new),
    ("Dériver une variante", _action_derive),
    ("Clôturer un brouillon (conclure + committer)", _action_close_draft),
    ("Fusionner deux branches", _action_merge),
    ("Générer un rapport d'étude", _action_report),
    ("Générer le graphe de filiation", _action_graph),
]
_QUIT = "Quitter"


def run_menu(repo_path: str = DEFAULT_REPO) -> int:
    """Entry point for ``follow menu``: an interactive loop over :data:`_ACTIONS`, each wrapping
    the same :class:`~follow.repository.Repository` calls the scriptable subcommands use. A
    mistake in one action (a validation error, a bad path) is reported and returns to the menu
    rather than crashing the session - the same errors the scriptable CLI would raise, just not
    fatal here.
    """
    _require_questionary()
    repo = _repo(repo_path)
    questionary.print(f"Follow — dépôt : {repo_path}  ({len(repo)} expérience(s))", style="bold")
    while True:
        choice = questionary.select("Que voulez-vous faire ?", choices=[label for label, _ in _ACTIONS] + [_QUIT]).ask()
        if choice is None or choice == _QUIT:
            return 0
        action = next(fn for label, fn in _ACTIONS if label == choice)
        try:
            action(repo)
        except (FollowError, SystemExit, ValueError, KeyError) as exc:
            questionary.print(f"Erreur : {exc}", style="fg:red")
