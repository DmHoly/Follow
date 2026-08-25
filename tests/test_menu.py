"""Tests for follow/menu.py: each interactive action, driven by a scripted queue of canned
answers standing in for questionary's .ask() - the same wiring a real terminal session would
exercise, without needing a real terminal.
"""

import json

import pytest

from examples.recipe import CakeRecipe
from follow import Quantity, Repository
from follow.commit_form import CommitForm
from follow.menu import (
    _action_close_draft,
    _action_derive,
    _action_graph,
    _action_list,
    _action_merge,
    _action_new,
    _action_report,
    _action_show,
    _collect_form_answers,
    _require_questionary,
    questionary,
    run_menu,
)


class _Fake:
    def __init__(self, value):
        self._value = value

    def ask(self):
        return self._value


def _script(monkeypatch, answers):
    """Replace every questionary prompt with one that pops the next canned answer, in the order
    the action under test asks for them. ``questionary.print`` is silenced but recorded, for
    assertions that check what was shown.

    The queue is positional, which is the nature of scripting a wizard - but running out used to
    fail with a bare "asked for more answers than the test scripted", leaving you to work out
    *which* prompt from a list of a dozen bare values. The transcript below names the prompt that
    ran out and replays everything answered before it, so a question inserted mid-action points
    straight at itself instead of at the tail of the queue.
    """
    queue = iter(list(answers))

    class _Printed(list):
        transcript: list = []

    printed = _Printed()
    transcript = []

    def _prompt(kind):
        def _ask(*args, **_kwargs):
            message = str(args[0]) if args else ""
            try:
                value = next(queue)
            except StopIteration:
                raise AssertionError(
                    f"the action asked for an answer the test did not script: "
                    f"{kind}({message!r}).\nAlready answered, in order:\n  "
                    + "\n  ".join(f"{i}. {k}({m!r}) -> {v!r}" for i, (k, m, v) in enumerate(transcript, 1))
                ) from None
            transcript.append((kind, message, value))
            return _Fake(value)

        return _ask

    for kind in ("text", "select", "confirm", "checkbox", "path"):
        monkeypatch.setattr(questionary, kind, _prompt(kind))
    monkeypatch.setattr(questionary, "print", lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
    printed.transcript = transcript  # type: ignore[attr-defined]
    return printed


def _cake_json(tmp_path, flour_g=200):
    path = tmp_path / "cake.json"
    path.write_text(json.dumps({
        "name": "Vanilla cake",
        "ingredients": {"flour": {"value": flour_g, "unit": "g"}},
        "bake": {"temperature": {"value": 180, "unit": "C"}, "duration": {"value": 35, "unit": "min"}},
    }))
    return str(path)


def test_require_questionary_raises_a_clean_error_when_not_installed(monkeypatch):
    monkeypatch.setattr("follow.menu.questionary", None)
    with pytest.raises(SystemExit, match="questionary"):
        _require_questionary()


def test_action_new_declares_and_commits_an_experiment(tmp_path, monkeypatch):
    printed = _script(monkeypatch, [
        "main", "v1", "test intent", "",             # branch, title, intent, hypothesis
        "examples.recipe.CakeRecipe", _cake_json(tmp_path),  # structure type + file
        False,                                         # add objective? no
        False,                                         # add evidence? no
        False,                                         # conclude now? no
        True,                                           # commit now? yes
    ])
    repo = Repository()
    _action_new(repo)

    assert len(repo) == 1
    exp = next(iter(repo))
    assert exp.branch == "main" and exp.title == "v1" and exp.intent == "test intent"
    assert any("Committé" in line for line in printed)


def test_action_new_with_objective_and_evidence_and_conclusion(tmp_path, monkeypatch):
    _script(monkeypatch, [
        "main", "v1", "test intent", "some hypothesis",
        "examples.recipe.CakeRecipe", _cake_json(tmp_path),
        True,                                    # add objective? yes
        "Rise", "height_cm", "maximize", "5.0", "taller is better",
        False,                                   # add another objective? no
        True,                                    # add evidence? yes
        "ev1", "oven log", "file:///log.jpg",
        False,                                   # add another evidence? no
        True,                                    # conclude now? yes
        "concluded", "promote", "Rose nicely.", "Scale up.",
        True,                                    # result for objective "Rise"? yes
        "met", "5.4", "cm", "Above target",       # verdict, observed value, unit, reasoning
        ["ev1"],                                 # cited evidence
        True,                                    # commit now? yes
    ])
    repo = Repository()
    _action_new(repo)

    exp = next(iter(repo))
    assert exp.objectives[0].name == "Rise"
    assert exp.evidence[0].id == "ev1"
    assert exp.conclusion.decision == "promote"
    assert exp.conclusion.next_steps == "Scale up."
    result = exp.conclusion.objective_results[0]
    assert result.evidence_ids == ["ev1"]
    assert result.observed == Quantity(value=5.4, unit="cm")
    assert result.reasoning == "Above target"


def test_action_new_requires_title_and_intent(monkeypatch):
    printed = _script(monkeypatch, ["main", "", "some intent"])
    repo = Repository()
    _action_new(repo)
    assert len(repo) == 0
    assert any("requis" in line for line in printed)


def test_action_derive_continues_the_parent_branch(tmp_path, monkeypatch):
    repo = Repository()
    baseline = repo.new(
        branch="main", structure=CakeRecipe.model_validate(json.loads(open(_cake_json(tmp_path)).read())),
        title="Baseline", intent="start",
    ).commit()

    _script(monkeypatch, [
        baseline.id,                    # pick parent (questionary.select choice value)
        "More flour", "does it help?",  # title, intent
        "",                              # new branch: empty -> continue parent's branch
        False,                          # replace structure? no
        False, False, False,            # objectives/evidence/conclude: no
        True,                            # commit now
    ])
    _action_derive(repo)

    assert len(repo) == 2
    assert repo.branches["main"] != baseline.id  # advanced


def test_action_close_draft_completes_and_commits(tmp_path, monkeypatch):
    repo = Repository()
    builder = repo.new(
        branch="main", structure=CakeRecipe.model_validate(json.loads(open(_cake_json(tmp_path)).read())),
        title="Draft", intent="start",
    )
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(builder.to_draft()))

    _script(monkeypatch, [
        str(draft_path),
        True, "concluded", "(aucune)", "Wrapped up.", "",  # conclude now + fields (no objectives to loop over)
    ])
    _action_close_draft(repo)

    assert len(repo) == 1
    exp = next(iter(repo))
    assert exp.conclusion.status == "concluded"
    assert exp.conclusion.summary == "Wrapped up."


def test_action_merge_takes_selected_paths(tmp_path, monkeypatch):
    repo = Repository()
    cake = CakeRecipe.model_validate(json.loads(open(_cake_json(tmp_path)).read()))
    v1 = repo.new(branch="main", structure=cake, title="Baseline", intent="start").commit()

    branch = repo.derive(v1.id, new_branch="feature", title="Feature", intent="try something")
    branch.structure.ingredients["flour"] = Quantity(value=300, unit="g")
    feature_tip = branch.commit()

    _script(monkeypatch, [
        "main", "feature",              # ref_a, ref_b
        ["ingredients.flour"],          # take_structure (checkbox) - steps are identical, no step-diff prompt fires
        "Merge", "merge it",            # title, intent
        False,                          # conclude now? no
        True,                            # commit now? yes
    ])
    _action_merge(repo)

    merged = repo.branches["main"]
    assert repo.get(merged).id != v1.id
    assert repo.load_structure(repo.get(merged)).ingredients["flour"].value == 300
    assert feature_tip.id in repo.get(merged).parents


def test_action_merge_requires_at_least_two_branches(monkeypatch):
    printed = _script(monkeypatch, [])
    repo = Repository()
    _action_merge(repo)
    assert any("deux branches" in line for line in printed)


def test_action_list_prints_branches_and_tags(tmp_path, monkeypatch):
    repo = Repository()
    cake = CakeRecipe.model_validate(json.loads(open(_cake_json(tmp_path)).read()))
    v1 = repo.new(branch="main", structure=cake, title="Baseline", intent="start").commit()
    repo.tag("v1-tag", v1.id)

    printed = _script(monkeypatch, [])
    _action_list(repo)
    joined = "\n".join(printed)
    assert "main" in joined
    assert "v1-tag" in joined


def test_action_show_renders_the_fiche(tmp_path, monkeypatch):
    repo = Repository()
    cake = CakeRecipe.model_validate(json.loads(open(_cake_json(tmp_path)).read()))
    v1 = repo.new(branch="main", structure=cake, title="Baseline", intent="start").commit()

    printed = _script(monkeypatch, [v1.id])
    _action_show(repo)
    assert any("Baseline" in line for line in printed)


def test_action_report_writes_html_without_opening_a_browser(tmp_path, monkeypatch):
    repo = Repository()
    cake = CakeRecipe.model_validate(json.loads(open(_cake_json(tmp_path)).read()))
    repo.new(branch="main", structure=cake, title="Baseline", intent="start").commit()

    out = tmp_path / "report.html"
    printed = _script(monkeypatch, [str(out), False])  # out path, then "open in browser?" no
    _action_report(repo)

    assert out.exists()
    assert "<title>" in out.read_text()
    assert any("écrit" in line for line in printed)


def test_action_graph_writes_html_without_opening_a_browser(tmp_path, monkeypatch):
    repo = Repository()
    cake = CakeRecipe.model_validate(json.loads(open(_cake_json(tmp_path)).read()))
    repo.new(branch="main", structure=cake, title="Baseline", intent="start").commit()

    out = tmp_path / "graph.html"
    printed = _script(monkeypatch, [str(out), False])
    _action_graph(repo)

    assert out.exists()
    assert any("écrit" in line for line in printed)


FORM = CommitForm.model_validate({
    "title": "Formulaire de commit",
    "fields": [
        {"name": "operateur", "label": "Opérateur", "type": "string", "required": True},
        {"name": "type_plan", "label": "Type de plan", "type": "choice", "choices": ["sweep", "confirmation"], "required": True},
        {"name": "verifie", "label": "Vérifié ?", "type": "boolean", "required": True},
    ],
})


def test_collect_form_answers_is_a_no_op_without_a_commit_form(tmp_path, monkeypatch):
    printed = _script(monkeypatch, [])  # would fail loudly if any prompt were called
    repo = Repository()
    builder = repo.new(branch="main", structure=CakeRecipe.model_validate(json.loads(open(_cake_json(tmp_path)).read())), title="t", intent="i")
    _collect_form_answers(repo, builder)
    assert builder.form_answers == {}
    assert printed == []


def test_collect_form_answers_populates_the_builder(tmp_path, monkeypatch):
    _script(monkeypatch, ["Alice", "confirmation", True])
    repo = Repository(commit_form=FORM)
    builder = repo.new(branch="main", structure=CakeRecipe.model_validate(json.loads(open(_cake_json(tmp_path)).read())), title="t", intent="i")
    _collect_form_answers(repo, builder)
    assert builder.form_answers == {"operateur": "Alice", "type_plan": "confirmation", "verifie": True}


def test_action_new_with_a_configured_commit_form_prompts_and_commits_successfully(tmp_path, monkeypatch):
    # this is the exact scenario that used to lose an entire filled-in wizard: a repo with a
    # commit form configured, driven through _action_new, must actually get to answer it.
    printed = _script(monkeypatch, [
        "main", "v1", "test intent", "",
        "examples.recipe.CakeRecipe", _cake_json(tmp_path),
        False, False, False,             # objectives/evidence/conclude: no
        "Alice", "sweep", False,          # commit form: operateur, type_plan, verifie
        True,                              # commit now? yes
    ])
    repo = Repository(commit_form=FORM)
    _action_new(repo)

    assert len(repo) == 1
    exp = next(iter(repo))
    assert exp.form_answers == {"operateur": "Alice", "type_plan": "sweep", "verifie": False}
    assert any("Committé" in line for line in printed)


def test_run_menu_quits_immediately(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _script(monkeypatch, ["Quitter"])
    assert run_menu(str(tmp_path / "repo")) == 0


def test_run_menu_recovers_from_an_action_error_instead_of_crashing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    printed = _script(monkeypatch, [
        "Démarrer une nouvelle expérience",
        "main", "v1", "intent", "",
        "not.a.real.module.Class",  # _load_structure_class raises SystemExit
        "Quitter",
    ])
    assert run_menu(str(tmp_path / "repo")) == 0
    assert any("Erreur" in line for line in printed)
