from pathlib import Path

import pytest
from pydantic import ValidationError

from examples.recipe import BakeStep, CakeRecipe
from follow import FormValidationError, Quantity, Repository
from follow.storage.commit_form import CommitForm, load_commit_form

FORM = {
    "title": "Formulaire de commit",
    "fields": [
        {"name": "operator", "label": "Opérateur", "type": "string", "required": True},
        {"name": "risk", "label": "Niveau de risque", "type": "choice", "choices": ["faible", "moyen", "élevé"], "required": True},
        {"name": "wafer_count", "label": "Nombre de wafers", "type": "number", "required": False},
        {"name": "checked_confounding", "label": "Confusion vérifiée ?", "type": "boolean", "required": False},
        {"name": "notes", "label": "Notes", "type": "text", "required": False},
    ],
}


def _cake() -> CakeRecipe:
    return CakeRecipe(
        name="Vanilla cake",
        ingredients={"flour": Quantity(value=200, unit="g")},
        bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def test_choice_field_without_choices_is_rejected():
    with pytest.raises(ValidationError, match="choices"):
        CommitForm.model_validate({"title": "x", "fields": [{"name": "a", "label": "A", "type": "choice"}]})


def test_non_choice_field_with_choices_is_rejected():
    with pytest.raises(ValidationError, match="choices"):
        CommitForm.model_validate({"title": "x", "fields": [{"name": "a", "label": "A", "type": "string", "choices": ["x"]}]})


def test_duplicate_field_names_are_rejected():
    with pytest.raises(ValidationError, match="dupliqués"):
        CommitForm.model_validate(
            {"title": "x", "fields": [{"name": "a", "label": "A"}, {"name": "a", "label": "A bis"}]}
        )


def test_validate_answers_reports_every_missing_required_field_at_once():
    form = CommitForm.model_validate(FORM)
    with pytest.raises(FormValidationError) as exc_info:
        form.validate_answers({})
    assert len(exc_info.value.errors) == 2  # operator + risk, both required
    assert any("operator" in e for e in exc_info.value.errors)
    assert any("risk" in e for e in exc_info.value.errors)


def test_validate_answers_rejects_unknown_fields():
    form = CommitForm.model_validate(FORM)
    with pytest.raises(FormValidationError, match="typo_field"):
        form.validate_answers({"operator": "Alice", "risk": "faible", "typo_field": "oops"})


def test_validate_answers_type_checks_each_field():
    form = CommitForm.model_validate(FORM)
    with pytest.raises(FormValidationError, match="operator"):
        form.validate_answers({"operator": 42, "risk": "faible"})
    with pytest.raises(FormValidationError, match="wafer_count"):
        form.validate_answers({"operator": "Alice", "risk": "faible", "wafer_count": "not a number"})
    with pytest.raises(FormValidationError, match="checked_confounding"):
        form.validate_answers({"operator": "Alice", "risk": "faible", "checked_confounding": "yes"})
    with pytest.raises(FormValidationError, match="risk"):
        form.validate_answers({"operator": "Alice", "risk": "extreme"})


def test_validate_answers_accepts_a_fully_valid_submission_and_drops_nothing_extraneous():
    form = CommitForm.model_validate(FORM)
    validated = form.validate_answers({"operator": "Alice", "risk": "faible", "wafer_count": 25, "checked_confounding": True})
    assert validated == {"operator": "Alice", "risk": "faible", "wafer_count": 25, "checked_confounding": True}


def test_optional_fields_can_be_omitted():
    form = CommitForm.model_validate(FORM)
    validated = form.validate_answers({"operator": "Alice", "risk": "faible"})
    assert validated == {"operator": "Alice", "risk": "faible"}


def test_load_commit_form_reads_yaml(tmp_path: Path):
    path = tmp_path / "commit_form.yml"
    path.write_text(
        "title: Formulaire\nfields:\n  - name: operator\n    label: Opérateur\n    type: string\n    required: true\n"
    )
    form = load_commit_form(path)
    assert form.title == "Formulaire"
    assert form.fields[0].name == "operator"


def test_repository_with_no_commit_form_never_validates_answers():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.answer_form(anything="goes", no_schema="at all")
    exp = builder.commit()
    assert exp.form_answers == {"anything": "goes", "no_schema": "at all"}


def test_repository_with_a_commit_form_refuses_a_commit_missing_required_answers():
    form = CommitForm.model_validate(FORM)
    repo = Repository(commit_form=form)
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    with pytest.raises(FormValidationError):
        builder.commit()
    assert len(repo) == 0  # nothing partially committed


def test_repository_with_a_commit_form_accepts_a_valid_submission():
    form = CommitForm.model_validate(FORM)
    repo = Repository(commit_form=form)
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.answer_form(operator="Alice", risk="faible")
    exp = builder.commit()
    assert exp.form_answers == {"operator": "Alice", "risk": "faible"}


def test_answer_form_merges_across_multiple_calls():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.answer_form(a=1)
    builder.answer_form(b=2)
    assert builder.form_answers == {"a": 1, "b": 2}


def test_repository_auto_detects_commit_form_yml_in_its_directory(tmp_path: Path):
    (tmp_path / "commit_form.yml").write_text(
        "title: Formulaire\nfields:\n  - name: operator\n    label: Opérateur\n    type: string\n    required: true\n"
    )
    repo = Repository(tmp_path)
    assert repo.commit_form is not None
    assert repo.commit_form.title == "Formulaire"

    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    with pytest.raises(FormValidationError):
        builder.commit()


def test_repository_accepts_a_commit_form_path_directly(tmp_path: Path):
    form_path = tmp_path / "form.yml"
    form_path.write_text(
        "title: Formulaire\nfields:\n  - name: operator\n    label: Opérateur\n    type: string\n    required: true\n"
    )
    repo = Repository(commit_form=form_path)
    assert repo.commit_form is not None
    assert repo.commit_form.title == "Formulaire"


def test_repository_reload_preserves_form_answers(tmp_path: Path):
    repo = Repository(tmp_path)
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.answer_form(operator="Alice")
    exp = builder.commit()

    reloaded = Repository(tmp_path)
    assert reloaded.get(exp.id).form_answers == {"operator": "Alice"}


def test_draft_round_trip_preserves_form_answers():
    repo = Repository()
    builder = repo.new(branch="main", structure=_cake(), title="v1", intent="x")
    builder.answer_form(operator="Alice")
    draft = builder.to_draft()
    assert draft["form_answers"] == {"operator": "Alice"}

    reloaded_builder = repo.load_draft(draft)
    assert reloaded_builder.form_answers == {"operator": "Alice"}
