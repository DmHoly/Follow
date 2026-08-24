"""Tests for follow/menu.py: each interactive action, driven by a scripted queue of canned
answers standing in for questionary's .ask() - the same wiring a real terminal session would
exercise, without needing a real terminal.
"""

import json

import pytest

from examples.recipe import CakeRecipe
from follow import Quantity, Repository
from follow.menu import (
    _action_close_draft,
    _action_derive,
    _action_graph,
    _action_list,
    _action_merge,
    _action_new,
    _action_report,
    _action_show,
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
    """Replace every questionary prompt function with one that pops the next canned answer, in
    the exact order the action under test calls them. questionary.print is silenced but recorded
    for assertions that need to check what was shown.
    """
    queue = iter(answers)
    printed = []

    def _next(*_args, **_kwargs):
        try:
            return _Fake(next(queue))
        except StopIteration:
            raise AssertionError("action asked for more answers than the test scripted") from None

    monkeypatch.setattr(questionary, "text", _next)
    monkeypatch.setattr(questionary, "select", _next)
    monkeypatch.setattr(questionary, "confirm", _next)
    monkeypatch.setattr(questionary, "checkbox", _next)
    monkeypatch.setattr(questionary, "path", _next)
    monkeypatch.setattr(questionary, "print", lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
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
        "met", "Above target",
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
    assert exp.conclusion.objective_results[0].evidence_ids == ["ev1"]


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
