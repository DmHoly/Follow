"""A YAML-defined questionnaire a :class:`~follow.repository.Repository` can require answers to
before it accepts a commit - metadata that isn't part of the domain ``Structure`` (an operator
name, a fab run id, why this particular split was chosen, whether crossed factors were checked
for confounding...) but that you want captured, structured, and validated every time, not left
to whoever remembers to write a good commit message.

The template is authored once as plain YAML (:func:`load_commit_form`), not Python, so it can be
edited by someone who isn't writing code, and so the same file can later drive an actual form UI
instead of only a hand-edited draft JSON's ``form_answers`` key - the field types
(:class:`FormField`) are exactly what a form renderer needs (label, type, choices, required).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# re-exported so `from follow.commit_form import FormValidationError` keeps working
from .errors import FormValidationError  # noqa: F401


class FormField(BaseModel):
    """One question in a :class:`CommitForm`. ``type`` drives both validation here and, later,
    which input widget a GUI would render for it.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    type: Literal["string", "text", "number", "boolean", "choice"] = "string"
    required: bool = True
    choices: list[str] | None = None
    help: str | None = None

    @model_validator(mode="after")
    def _check_choices_match_type(self) -> "FormField":
        if self.type == "choice" and not self.choices:
            raise ValueError(f"le champ {self.name!r} est de type 'choice' mais n'a pas de 'choices'")
        if self.type != "choice" and self.choices is not None:
            raise ValueError(f"le champ {self.name!r} a des 'choices' mais n'est pas de type 'choice'")
        return self

    def check(self, value: Any) -> str | None:
        """Type-check one answer against this field; return an error message, or ``None``."""
        if self.type in ("string", "text"):
            if not isinstance(value, str):
                return f"{self.name!r} doit être une chaîne (reçu {type(value).__name__})"
        elif self.type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return f"{self.name!r} doit être un nombre (reçu {type(value).__name__})"
        elif self.type == "boolean":
            if not isinstance(value, bool):
                return f"{self.name!r} doit être un booléen (reçu {type(value).__name__})"
        elif self.type == "choice":
            if value not in (self.choices or []):
                return f"{self.name!r} doit être l'une de {self.choices} (reçu {value!r})"
        return None


class CommitForm(BaseModel):
    """A questionnaire template: a title plus an ordered list of :class:`FormField`. Attach one
    to a :class:`~follow.repository.Repository` (via ``commit_form=`` or a ``commit_form.yml``
    file dropped into the repository directory) to make answering it mandatory before any commit
    is accepted.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str | None = None
    fields: list[FormField] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_field_names_are_unique(self) -> "CommitForm":
        seen: set[str] = set()
        duplicates: set[str] = set()
        for field in self.fields:
            if field.name in seen:
                duplicates.add(field.name)
            seen.add(field.name)
        if duplicates:
            raise ValueError(f"noms de champ dupliqués dans le formulaire : {sorted(duplicates)}")
        return self

    def validate_answers(self, answers: dict[str, Any]) -> dict[str, Any]:
        """Check ``answers`` against every field and return the validated subset (only the
        fields actually defined by this form - anything else in ``answers`` is itself an error,
        not silently dropped). Raises :class:`FormValidationError` listing every problem found.
        """
        errors: list[str] = []
        validated: dict[str, Any] = {}
        known = {field.name for field in self.fields}
        unknown = sorted(set(answers) - known)
        if unknown:
            errors.append(f"champ(s) inconnu(s) du formulaire : {unknown}")

        for field in self.fields:
            value = answers.get(field.name)
            missing = value is None or (isinstance(value, str) and not value.strip())
            if missing:
                if field.required:
                    errors.append(f"{field.name!r} ({field.label}) est obligatoire")
                continue
            error = field.check(value)
            if error is not None:
                errors.append(error)
            else:
                validated[field.name] = value

        if errors:
            raise FormValidationError(errors)
        return validated


def load_commit_form(path: str | Path) -> CommitForm:
    """Read and validate a commit form template from a YAML file."""
    text = Path(path).read_text(encoding="utf-8")
    payload = yaml.safe_load(text) or {}
    return CommitForm.model_validate(payload)
