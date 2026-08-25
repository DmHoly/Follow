"""Every error Follow raises, in one hierarchy under :class:`FollowError`.

``FollowError`` was always documented as "the base class for Follow errors", but half the library
raised bare ``ValueError``/``KeyError`` instead: :meth:`Repository.merge
<follow.storage.repository.Repository.merge>` a ``ValueError``, :meth:`Structure.resolve
<follow.core.structure.Structure.resolve>` a ``KeyError``, :func:`~follow.paths.merging.split_path` a
``ValueError``, ``CommitForm`` a ``ValueError``... So ``except FollowError`` around a commit let
the most expected failure of all - an unanswered commit form - straight through, and the CLI had
to write ``except (FollowError, ValueError, KeyError, IndexError, TypeError)`` to catch one call.
When a caller needs five types for one call, the hierarchy is what is missing.

Each class also keeps the builtin it used to be, so code already catching ``ValueError`` or
``KeyError`` (including ``except KeyError`` around a dict-like lookup) keeps working unchanged.
This module deliberately imports nothing from the rest of the package, so any module can raise
from it without a circular import.
"""

from __future__ import annotations


class FollowError(Exception):
    """Base class for every error Follow raises."""


class ExperimentNotFoundError(FollowError, KeyError):
    """No experiment, branch or tag matches the given ref."""

    def __init__(self, ref: str, message: str | None = None):
        super().__init__(message or f"No experiment, branch or tag matches {ref!r}")
        self.ref = ref


class DanglingRefError(ExperimentNotFoundError):
    """A branch, tag or parent link points at an experiment the repository does not have - a
    ``refs.json`` that has drifted out of step with ``objects/`` (a half-finished copy, a deleted
    object file, an interrupted write).

    It is a kind of :class:`ExperimentNotFoundError` on purpose: callers already guarding for
    "this ref doesn't resolve" keep working, and ``ref in repo`` still answers False for it,
    matching what :meth:`Repository.get <follow.storage.repository.Repository.get>` will actually do. What
    it adds is a message that says the repository is inconsistent rather than that the name is
    unknown - the two call for very different fixes.
    """

    def __init__(self, kind: str, name: str, target_id: str):
        super().__init__(
            name,
            f"{kind} {name!r} points at {target_id}, which is not in this repository - its "
            "refs are out of step with its stored objects; point it somewhere real with "
            "repo.branch(..., force=True) / repo.tag(..., force=True), or restore the missing "
            "object file",
        )
        self.kind = kind
        self.target_id = target_id


class NothingToCommitError(FollowError):
    """A commit's content is identical to its target branch's current tip - the same rule as
    `git commit` refusing with "nothing to commit, working tree clean": Follow never creates a
    new commit that says nothing a prior one didn't already say.
    """

    def __init__(self, branch: str, tip_id: str):
        super().__init__(f"nothing to commit: {branch!r} already points at {tip_id}, and this commit's content is identical")
        self.branch = branch
        self.tip_id = tip_id


class StructureTypeError(FollowError, KeyError):
    """A ``structure_type`` key does not resolve to a registered :class:`~follow.core.structure.Structure`
    subclass - usually because the module defining it has not been imported yet.
    """


class MergeError(FollowError, ValueError):
    """Two experiments cannot be merged as asked - they are the same commit, or they describe
    different domains.
    """


class MalformedPathError(FollowError, ValueError):
    """A dotted/indexed path is not parseable (a non-numeric index, an unclosed bracket)."""


class PathNotFoundError(FollowError, KeyError):
    """A path does not exist on the structure it is being read from or written to."""


class BatchShapeError(FollowError, KeyError):
    """The entities handed to :func:`~follow.doe.batch.analyze_batch` do not share one shape, so
    there is no meaningful set of parameters to compare across them.
    """


class DesignError(FollowError, ValueError):
    """A design cannot be built as specified - an unknown factor name, a generator referring to a
    factor that does not exist, a design with no base factor.
    """


class FormValidationError(FollowError, ValueError):
    """A commit's ``form_answers`` don't satisfy the repository's commit form template - missing
    required fields, wrong types, or a choice outside the allowed list. Lists every problem at
    once, not just the first: this is meant to eventually drive a form UI, where showing every
    invalid field together is far more useful than stopping at the first one.
    """

    def __init__(self, errors: list[str]):
        super().__init__("réponses au formulaire invalides :\n  - " + "\n  - ".join(errors))
        self.errors = errors
