__version__ = "0.1.0"

from .batch import BatchFactor, BatchVariation, analyze_batch
from .commit_form import CommitForm, FormField, FormValidationError, load_commit_form
from .design import (
    FractionalFactorial,
    alias_structure,
    arange,
    check_identifiability,
    fractional_factorial,
    full_factorial,
    latin_hypercube,
    lin,
    log,
    sweep,
)
from .diffing import DiffEntry, StructureDiff, diff_structures
from .entities import find_entity_mentions
from .formatting import format_value, is_quantity_leaf
from .graphing import build_graph_figure, render_graph_html
from .merging import get_path, resolve_merge_paths, split_path
from .models import (
    Conclusion,
    Evidence,
    Experiment,
    Objective,
    ObjectiveResult,
    ReferenceLink,
    Step,
)
from .quantity import Quantity
from .rendering import render_fiche, render_log
from .report import batch_table, experiment_fiche, render_study_html
from .errors import (
    BatchShapeError,
    DanglingRefError,
    DesignError,
    ExperimentNotFoundError,
    FollowError,
    MalformedPathError,
    MergeError,
    NothingToCommitError,
    PathNotFoundError,
    StructureTypeError,
)
from .repository import ExperimentBuilder, Repository
from .structure import Structure

__all__ = [
    "__version__",
    "alias_structure",
    "analyze_batch",
    "arange",
    "batch_table",
    "BatchFactor",
    "BatchShapeError",
    "BatchVariation",
    "build_graph_figure",
    "check_identifiability",
    "CommitForm",
    "Conclusion",
    "DanglingRefError",
    "DesignError",
    "diff_structures",
    "DiffEntry",
    "Evidence",
    "Experiment",
    "experiment_fiche",
    "ExperimentBuilder",
    "ExperimentNotFoundError",
    "find_entity_mentions",
    "FollowError",
    "format_value",
    "FormField",
    "FormValidationError",
    "fractional_factorial",
    "FractionalFactorial",
    "full_factorial",
    "get_path",
    "is_quantity_leaf",
    "latin_hypercube",
    "lin",
    "load_commit_form",
    "log",
    "MalformedPathError",
    "MergeError",
    "NothingToCommitError",
    "Objective",
    "ObjectiveResult",
    "PathNotFoundError",
    "Quantity",
    "ReferenceLink",
    "render_fiche",
    "render_graph_html",
    "render_log",
    "render_study_html",
    "Repository",
    "resolve_merge_paths",
    "split_path",
    "Step",
    "Structure",
    "StructureDiff",
    "StructureTypeError",
    "sweep",
]
