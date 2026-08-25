"""The FastAPI application: Follow's :class:`~follow.storage.repository.Repository` exposed as a REST
API, plus the static GUI (see ``follow/api/static/``) served from the same process.

Only one repository is served per running app - see :func:`create_app`. Structure types are
Python classes, not data, so this module cannot invent them: it imports the module of every
``structure_type`` already used in the repository (so existing experiments render and diff), and
optionally a list of extra dotted module paths (so a *new* structure type - one nothing has been
committed with yet - shows up in the "new experiment" form too).
"""

from __future__ import annotations

import importlib
import sys
import typing
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from ..doe.batch import analyze_batch
from ..storage.commit_form import FormValidationError
from ..doe.design import DesignError, check_identifiability, fractional_factorial, full_factorial, latin_hypercube, sweep
from ..paths.diffing import StructureDiff
from ..paths.entities import list_entity_ids
from ..core.errors import BatchShapeError, ExperimentNotFoundError, FollowError, MergeError, NothingToCommitError, StructureTypeError
from ..core.models import Conclusion, Evidence, Experiment, Objective, ReferenceLink, Step
from ..presentation.rendering import render_fiche
from ..storage.repository import Repository
from ..core.structure import Structure

STATIC_DIR = Path(__file__).parent / "static"
REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_BUILD_DIR = REPO_ROOT / "docs" / "_build" / "html"
EXAMPLES_DIR = REPO_ROOT / "demos" / "output"

RUNNING_STATUSES = {"draft", "running"}
COMPLETED_STATUSES = {"concluded", "abandoned"}

# A small curated manifest of the demo reports under demos/output/ - see demos/README.md,
# which these descriptions are lifted from. Listed here (rather than discovered generically)
# so the "Exemples" page can show a title and a one-line description per report, not just a
# bare filename; entries whose file does not actually exist (e.g. a wheel install with no
# demos/ directory) are filtered out in the endpoint below rather than raising.
EXAMPLES_MANIFEST = [
    {
        "file": "chocolate_cake_optimization.html",
        "title": "Guide complet : optimisation d'un gâteau au chocolat",
        "description": (
            "Le scénario de bout en bout : intention, structure, référence et objectifs, un split "
            "manuel puis factoriel, un plan fractionnaire, un screening, la fusion de deux "
            "améliorations validées séparément, un formulaire de commit obligatoire et une "
            "validation finale."
        ),
    },
    {
        "file": "fusion_selective.html",
        "title": "Fusion sélective (l'équivalent de git merge)",
        "description": (
            "Une recette à 5 étapes, une branche de test qui explore la cuisson sur 3 commits, une "
            "évolution indépendante sur main en parallèle, puis une fusion qui ne rapatrie que "
            "l'étape validée - la résolution de conflit chemin par chemin."
        ),
    },
    {
        "file": "chocolate_fondant.html",
        "title": "Optimisation d'un fondant au chocolat",
        "description": (
            "Dix recettes réelles synthétisées en une recette de référence, puis affinées par "
            "plusieurs expériences ciblées."
        ),
    },
    {
        "file": "chocolate_fondant_auto_report.html",
        "title": "Le même dépôt, en rapport 100% automatique",
        "description": (
            "Le même dépôt que ci-dessus, rendu par render_study_html sans aucune section écrite à "
            "la main - à comparer avec la version narrée pour voir la différence."
        ),
    },
    {
        "file": "wafer_doe.html",
        "title": "Plan factoriel 5×5 sur wafers",
        "description": (
            "Dose d'implantation × température de recuit sur 25 wafers, modélisé comme une seule "
            "expérience, suivi d'un lot de confirmation homogène - vue explosée par entité."
        ),
    },
    {
        "file": "entity_tracking.html",
        "title": "Suivi d'une entité physique",
        "description": (
            "Deux expériences sur des branches séparées, sans parent ni référence, reliées "
            "automatiquement par le seul nom physique qu'elles partagent."
        ),
    },
]


def _message(exc: FollowError) -> str:
    """The plain error message for ``exc``, not ``KeyError``'s quoted-repr ``str()``.

    A few of Follow's errors (:class:`~follow.core.errors.ExperimentNotFoundError`,
    :class:`~follow.core.errors.StructureTypeError`...) are deliberately also ``KeyError`` subclasses
    (see :mod:`follow.core.errors`), which means plain ``str(exc)`` returns ``repr(args[0])`` -
    doubly-quoted and backslash-escaped - instead of the message itself. Fine for a traceback,
    ugly in a JSON ``detail`` field a GUI displays as-is.
    """
    return str(exc.args[0]) if exc.args else str(exc)


def _import_dotted_module(dotted: str) -> None:
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    importlib.import_module(dotted)


def _import_known_structure_modules(repo: Repository, extra_modules: Iterable[str] = ()) -> list[str]:
    """Best-effort import of every structure module the repo's experiments already reference,
    plus ``extra_modules``. Returns the dotted module names that failed to import (rather than
    raising) - one broken/renamed structure module should not prevent the whole API from
    starting, just leave that one type unavailable until fixed.
    """
    modules = {exp.structure_type.rsplit(".", 1)[0] for exp in repo} | set(extra_modules)
    failed: list[str] = []
    for module in sorted(modules):
        try:
            _import_dotted_module(module)
        except ImportError:
            failed.append(module)
    return failed


# -- request bodies -----------------------------------------------------------------------


class NewExperimentRequest(BaseModel):
    branch: str
    structure_type: str
    structure: dict[str, Any]
    title: str
    intent: str
    author: str | None = None
    hypothesis: str | None = None
    parents: list[str] | None = None
    references: list[ReferenceLink] = Field(default_factory=list)
    objectives: list[Objective] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    conclusion: Conclusion | None = None
    tags: list[str] = Field(default_factory=list)
    form_answers: dict[str, Any] = Field(default_factory=dict)


class DeriveExperimentRequest(BaseModel):
    title: str
    intent: str
    new_branch: str | None = None
    structure: dict[str, Any] | None = None
    author: str | None = None
    hypothesis: str | None = None
    carry_objectives: bool = True
    carry_references: bool = True
    carry_steps: bool = True
    evidence: list[Evidence] = Field(default_factory=list)
    conclusion: Conclusion | None = None
    tags: list[str] = Field(default_factory=list)
    form_answers: dict[str, Any] = Field(default_factory=dict)


class MergeRequest(BaseModel):
    ref_a: str
    ref_b: str
    title: str
    intent: str
    take_structure: list[str] = Field(default_factory=list)
    take_steps: list[str] = Field(default_factory=list)
    branch: str | None = None
    author: str | None = None
    hypothesis: str | None = None
    form_answers: dict[str, Any] = Field(default_factory=dict)


class RefRequest(BaseModel):
    name: str
    at: str
    force: bool = False


class DesignPlanRequest(BaseModel):
    """One design-of-experiments plan - see :mod:`follow.doe.design` for what each ``type`` means.
    Fields irrelevant to the chosen ``type`` are simply ignored (e.g. ``values`` for a
    ``full_factorial`` plan), rather than one request schema per plan type, to keep the endpoint
    a single shape the GUI's DOE screen can post regardless of which plan the user picked.
    """

    type: str  # "sweep" | "full_factorial" | "latin_hypercube" | "fractional_factorial"
    id_field: str | None = None
    # sweep
    field: str | None = None
    values: list[Any] = Field(default_factory=list)
    # full_factorial: {field_name: [values...]}
    factors: dict[str, list[Any]] = Field(default_factory=dict)
    # latin_hypercube
    n: int | None = None
    seed: int | None = None
    factor_ranges: dict[str, list[Any]] = Field(default_factory=dict)  # [low, high] or [low, high, unit]
    # fractional_factorial: factors above as [low, high] or [low, high, unit]; generators map a
    # generated factor's name to the base factors whose sign-product defines it
    generators: dict[str, list[str]] = Field(default_factory=dict)


class DesignGenerateRequest(BaseModel):
    structure_type: str
    field: str
    reference: dict[str, Any]
    plan: DesignPlanRequest


def _experiment_payload(experiment: Experiment, repo: Repository) -> dict[str, Any]:
    batch_fields: list[str] = []
    try:
        structure_cls = Structure.resolve(experiment.structure_type)
    except StructureTypeError:
        structure_cls = None
    if structure_cls is not None:
        for name in _batch_fields(structure_cls):
            value = experiment.structure.get(name)
            if isinstance(value, list) and len(value) > 1:
                batch_fields.append(name)
    return {
        "experiment": experiment.model_dump(mode="json"),
        "fiche_markdown": render_fiche(experiment, repo),
        "entity_ids": list_entity_ids(experiment.structure),
        "batch_fields": batch_fields,
    }


def _list_item_structure_class(annotation: Any) -> type[Structure] | None:
    """If ``annotation`` is ``list[X]`` for some ``Structure`` subclass ``X``, return ``X`` -
    otherwise ``None``. This is how a "batch" field (an experiment holding many sibling entities,
    e.g. ``WaferLot.wafers: list[Wafer]`` - see :mod:`follow.doe.batch`) is told apart from an
    ordinary list field, generically, from the parent model's own field annotations - no
    per-domain configuration needed for the DOE generator to find where to plug in.
    """
    origin = typing.get_origin(annotation)
    if origin is not list:
        return None
    args = typing.get_args(annotation)
    if not args:
        return None
    item = args[0]
    if isinstance(item, type) and issubclass(item, Structure):
        return item
    return None


def _batch_fields(structure_cls: type[Structure]) -> dict[str, type[Structure]]:
    fields = {}
    for name, field_info in structure_cls.model_fields.items():
        entity_cls = _list_item_structure_class(field_info.annotation)
        if entity_cls is not None:
            fields[name] = entity_cls
    return fields


def create_app(
    repo_path: str | Path,
    *,
    structure_modules: Iterable[str] = (),
    title: str = "Follow API",
) -> FastAPI:
    """Build a FastAPI app serving the repository at ``repo_path``.

    ``structure_modules`` are extra dotted module paths to import at startup (beyond the
    modules already referenced by committed experiments), so a structure type nothing has been
    committed with yet still appears in ``GET /api/structures``.
    """
    repo = Repository(Path(repo_path))
    failed_imports = _import_known_structure_modules(repo, structure_modules)

    # docs_url/redoc_url disabled: FastAPI otherwise claims "/docs" itself for its interactive
    # Swagger UI, which silently wins over our own "/docs" mount (the Sphinx site) below - the
    # OpenAPI schema is still served at /openapi.json for anyone who wants it that way.
    app = FastAPI(title=title, docs_url=None, redoc_url=None)
    app.state.repo = repo
    app.state.repo_path = str(Path(repo_path))
    app.state.failed_structure_imports = failed_imports

    @app.exception_handler(FormValidationError)
    async def _form_validation_error(_request: Any, exc: FormValidationError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"detail": _message(exc), "errors": exc.errors})

    @app.exception_handler(ExperimentNotFoundError)
    async def _not_found(_request: Any, exc: ExperimentNotFoundError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": _message(exc)})

    @app.exception_handler(NothingToCommitError)
    async def _nothing_to_commit(_request: Any, exc: NothingToCommitError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"detail": _message(exc)})

    @app.exception_handler(MergeError)
    async def _merge_error(_request: Any, exc: MergeError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"detail": _message(exc)})

    @app.exception_handler(StructureTypeError)
    async def _structure_type_error(_request: Any, exc: StructureTypeError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"detail": _message(exc)})

    @app.exception_handler(ValidationError)
    async def _pydantic_validation_error(_request: Any, exc: ValidationError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"detail": "validation error", "errors": exc.errors()})

    @app.exception_handler(FollowError)
    async def _follow_error(_request: Any, exc: FollowError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"detail": _message(exc)})

    # -- read -----------------------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        running = sum(1 for exp in repo if exp.conclusion.status in RUNNING_STATUSES)
        completed = sum(1 for exp in repo if exp.conclusion.status in COMPLETED_STATUSES)
        return {
            "status": "ok",
            "repo": app.state.repo_path,
            "experiments": len(repo),
            "running": running,
            "completed": completed,
            "branches": len(repo.branches),
            "failed_structure_imports": app.state.failed_structure_imports,
        }

    @app.get("/api/branches")
    def branches() -> dict[str, str]:
        return repo.branches

    @app.get("/api/tags")
    def tags() -> dict[str, str]:
        return repo.tags

    @app.get("/api/structures")
    def structures() -> list[dict[str, str]]:
        return [{"key": key, "name": cls.__name__} for key, cls in sorted(Structure.registered().items())]

    @app.get("/api/structures/{key:path}/schema")
    def structure_schema(key: str) -> dict[str, Any]:
        try:
            cls = Structure.resolve(key)
        except StructureTypeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return cls.model_json_schema()

    @app.get("/api/commit_form")
    def commit_form() -> dict[str, Any] | None:
        if repo.commit_form is None:
            return None
        return repo.commit_form.model_dump(mode="json")

    @app.get("/api/structures/{key:path}/batch-fields")
    def batch_fields(key: str) -> list[dict[str, Any]]:
        """Which fields of structure type ``key`` hold a list of sibling entities (``list[X]``
        for some other registered ``Structure`` subclass ``X``) - e.g. ``WaferLot.wafers``. Each
        entry carries the entity type's own JSON Schema, so the GUI can build both a reference
        (baseline) form and the factor pickers for :func:`design_generate` without a second
        round-trip.
        """
        try:
            cls = Structure.resolve(key)
        except StructureTypeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return [
            {"field": name, "entity_type": entity_cls.registry_key(), "entity_schema": entity_cls.model_json_schema()}
            for name, entity_cls in _batch_fields(cls).items()
        ]

    @app.post("/api/design/generate")
    def design_generate(body: DesignGenerateRequest) -> dict[str, Any]:
        """Generate a batch of structural variants (a DOE split) for one "batch field" of a
        structure type, and analyze the result the same way ``follow explode`` does - so the GUI
        can show the constant/varying split ("the matrix") and an identifiability warning before
        anyone commits to it, not after.
        """
        try:
            parent_cls = Structure.resolve(body.structure_type)
        except StructureTypeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        entity_cls = _batch_fields(parent_cls).get(body.field)
        if entity_cls is None:
            raise HTTPException(
                status_code=400,
                detail=f"{body.field!r} n'est pas un champ de {body.structure_type!r} contenant une liste d'entités (Structure)",
            )
        reference = entity_cls.model_validate(body.reference)

        plan = body.plan
        resolution: int | None = None
        aliases: dict[str, list[str]] = {}
        factor_names: list[str]
        if plan.type == "sweep":
            if not plan.field:
                raise HTTPException(status_code=422, detail="plan 'sweep' : 'field' est requis")
            variants = sweep(reference, plan.field, plan.values, id_field=plan.id_field)
            factor_names = [plan.field]
        elif plan.type == "full_factorial":
            if not plan.factors:
                raise HTTPException(status_code=422, detail="plan 'full_factorial' : 'factors' est requis")
            variants = full_factorial(reference, id_field=plan.id_field, **plan.factors)
            factor_names = list(plan.factors)
        elif plan.type == "latin_hypercube":
            if not plan.n or not plan.factor_ranges:
                raise HTTPException(status_code=422, detail="plan 'latin_hypercube' : 'n' et 'factor_ranges' sont requis")
            ranges = {name: tuple(spec) for name, spec in plan.factor_ranges.items()}
            variants = latin_hypercube(reference, plan.n, seed=plan.seed, id_field=plan.id_field, **ranges)
            factor_names = list(plan.factor_ranges)
        elif plan.type == "fractional_factorial":
            if not plan.factors:
                raise HTTPException(status_code=422, detail="plan 'fractional_factorial' : 'factors' est requis")
            ranges = {name: tuple(spec) for name, spec in plan.factors.items()}
            result = fractional_factorial(reference, ranges, plan.generators, id_field=plan.id_field)
            variants, resolution, aliases = result.variants, result.resolution, result.aliases
            factor_names = list(plan.factors)
        else:
            raise HTTPException(status_code=422, detail=f"type de plan inconnu: {plan.type!r}")

        variation = analyze_batch(variants, ignore=[plan.id_field] if plan.id_field else [])
        try:
            identifiability = check_identifiability(variants, factor_names)
        except (TypeError, ValueError):
            # a non-numeric factor (a string level, say) can't be correlation-checked - the split
            # itself is still perfectly valid, so this is skipped rather than failing the request.
            identifiability = []

        return {
            "variants": [v.model_dump(mode="json") for v in variants],
            "variation": variation.model_dump(mode="json"),
            "identifiability": [{"a": a, "b": b, "correlation": corr} for a, b, corr in identifiability],
            "resolution": resolution,
            "aliases": aliases,
        }

    @app.get("/api/log/{ref}")
    def log(ref: str, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        """A page of ``ref``'s history, newest first - ``repo.log`` itself has no notion of
        paging (it always returns the full lineage), so the slicing happens here rather than
        asking every caller of ``Repository.log`` to know about pages that only the GUI needs.
        """
        if offset < 0:
            raise HTTPException(status_code=422, detail="offset doit être >= 0")
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=422, detail="limit doit être entre 1 et 500")
        history = repo.log(ref)
        page = history[offset : offset + limit]
        return {
            "items": [exp.model_dump(mode="json") for exp in page],
            "total": len(history),
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/experiments")
    def list_experiments(status: str = "all", offset: int = 0, limit: int = 50) -> dict[str, Any]:
        """Every experiment in the repository (unlike ``/api/log/{ref}``, which is one branch's
        first-parent lineage), newest first, optionally filtered by ``status``: ``running``
        (conclusion.status is ``draft``/``running``) or ``completed`` (``concluded``/``abandoned``).
        This is what backs the GUI's "en cours"/"terminées" dashboards.
        """
        if status not in ("all", "running", "completed"):
            raise HTTPException(status_code=422, detail="status doit être 'all', 'running' ou 'completed'")
        if offset < 0:
            raise HTTPException(status_code=422, detail="offset doit être >= 0")
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=422, detail="limit doit être entre 1 et 500")

        wanted = RUNNING_STATUSES if status == "running" else COMPLETED_STATUSES if status == "completed" else None
        matches = [exp for exp in repo if wanted is None or exp.conclusion.status in wanted]
        matches.sort(key=lambda exp: exp.created_at, reverse=True)
        page = matches[offset : offset + limit]
        return {
            "items": [exp.model_dump(mode="json") for exp in page],
            "total": len(matches),
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/examples")
    def list_examples() -> list[dict[str, str]]:
        """The curated demo reports under demos/output/ that actually exist on this install -
        see :data:`EXAMPLES_MANIFEST`. Each ``file`` is served at ``/examples-gallery/<file>``.
        """
        return [entry for entry in EXAMPLES_MANIFEST if (EXAMPLES_DIR / entry["file"]).exists()]

    @app.get("/api/graph")
    def graph() -> dict[str, list[str]]:
        return repo.graph()

    @app.get("/api/graph.html", response_class=HTMLResponse)
    def graph_html() -> str:
        """The lineage graph as a self-contained Plotly page - the same figure `follow graph`
        writes to a file, served directly so the GUI can embed it in an iframe.
        """
        from ..presentation.graphing import build_graph_figure

        if len(repo) == 0:
            return "<p style='font-family: sans-serif; padding: 1rem;'>Dépôt vide - rien à représenter.</p>"
        return build_graph_figure(repo).to_html(include_plotlyjs=True, full_html=True)

    # Registered before the generic "{ref:path}" experiment-lookup route below: {ref:path} is
    # greedy (it matches slashes too, so it accepts anything including "<id>/batch/<field>" as
    # one big ref) and FastAPI/Starlette match routes in registration order, so the generic route
    # would otherwise swallow every request meant for this one before it ever got a chance to run.
    @app.get("/api/experiments/{ref:path}/batch/{field}")
    def experiment_batch(ref: str, field: str) -> dict[str, Any]:
        """The constant/varying split (:func:`~follow.doe.batch.analyze_batch`) of one batch field
        of an already-committed experiment - the same analysis ``follow explode`` renders to a
        standalone HTML page, here as JSON for the GUI's "matrice de split" panel on a fiche.
        """
        experiment = repo.get(ref)
        entities = experiment.structure.get(field)
        if entities is None or not isinstance(entities, list):
            raise HTTPException(status_code=400, detail=f"{field!r} n'est pas un champ de liste sur cette expérience")
        try:
            variation = analyze_batch(entities)
        except BatchShapeError as exc:
            raise HTTPException(status_code=400, detail=_message(exc)) from exc
        return {"field": field, "variation": variation.model_dump(mode="json")}

    @app.get("/api/experiments/{ref:path}")
    def get_experiment(ref: str) -> dict[str, Any]:
        experiment = repo.get(ref)
        return _experiment_payload(experiment, repo)

    @app.get("/api/diff")
    def diff(a: str, b: str, steps: bool = False) -> dict[str, Any]:
        result: StructureDiff = repo.diff_steps(a, b) if steps else repo.diff(a, b)
        return result.model_dump(mode="json")

    @app.get("/api/entities/{entity_id}")
    def trace_entity(entity_id: str) -> list[dict[str, Any]]:
        return [exp.model_dump(mode="json") for exp in repo.find_entity(entity_id)]

    # -- write ----------------------------------------------------------------------------

    @app.post("/api/experiments", status_code=201)
    def new_experiment(body: NewExperimentRequest) -> dict[str, Any]:
        try:
            structure_cls = Structure.resolve(body.structure_type)
        except StructureTypeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        structure = structure_cls.model_validate(body.structure)
        builder = repo.new(
            branch=body.branch,
            structure=structure,
            title=body.title,
            intent=body.intent,
            author=body.author,
            hypothesis=body.hypothesis,
            parents=body.parents,
            references=body.references,
            objectives=body.objectives,
            steps=body.steps,
            tags=body.tags,
        )
        builder.evidence = list(body.evidence)
        if body.conclusion is not None:
            builder.conclusion = body.conclusion
        builder.answer_form(**body.form_answers)
        experiment = builder.commit()
        return _experiment_payload(experiment, repo)

    @app.post("/api/experiments/{ref:path}/derive", status_code=201)
    def derive_experiment(ref: str, body: DeriveExperimentRequest) -> dict[str, Any]:
        structure = None
        if body.structure is not None:
            parent = repo.get(ref)
            structure_cls = Structure.resolve(parent.structure_type)
            structure = structure_cls.model_validate(body.structure)
        builder = repo.derive(
            ref,
            title=body.title,
            intent=body.intent,
            new_branch=body.new_branch,
            structure=structure,
            author=body.author,
            hypothesis=body.hypothesis,
            carry_objectives=body.carry_objectives,
            carry_references=body.carry_references,
            carry_steps=body.carry_steps,
        )
        builder.evidence = list(body.evidence)
        if body.conclusion is not None:
            builder.conclusion = body.conclusion
        builder.tags = list(body.tags)
        builder.answer_form(**body.form_answers)
        experiment = builder.commit()
        return _experiment_payload(experiment, repo)

    @app.post("/api/merge", status_code=201)
    def merge_experiments(body: MergeRequest) -> dict[str, Any]:
        builder = repo.merge(
            body.ref_a,
            body.ref_b,
            title=body.title,
            intent=body.intent,
            take_structure=body.take_structure,
            take_steps=body.take_steps,
            branch=body.branch,
            author=body.author,
            hypothesis=body.hypothesis,
        )
        builder.answer_form(**body.form_answers)
        experiment = builder.commit()
        return _experiment_payload(experiment, repo)

    @app.post("/api/branches")
    def set_branch(body: RefRequest) -> dict[str, str]:
        repo.branch(body.name, body.at, force=body.force)
        return repo.branches

    @app.post("/api/tags")
    def set_tag(body: RefRequest) -> dict[str, str]:
        repo.tag(body.name, body.at, force=body.force)
        return repo.tags

    # -- GUI --------------------------------------------------------------------------------
    #
    # "/" is a sober landing page; the actual app lives under "/app" and is a client-routed
    # single-page app (see follow/api/static/app.js's router) - "/app" and every "/app/<path>"
    # serve the very same shell, so a deep link (a bookmark, a page refresh, a link someone
    # shares) lands on the right screen instead of a 404, with the JS router picking the route
    # up from ``location.pathname`` once the page loads.

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def landing() -> FileResponse:
            return FileResponse(STATIC_DIR / "landing.html")

        @app.get("/app")
        @app.get("/app/{_client_route:path}")
        def app_shell(_client_route: str = "") -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    if DOCS_BUILD_DIR.exists():
        app.mount("/docs", StaticFiles(directory=DOCS_BUILD_DIR, html=True), name="docs")
    else:

        @app.get("/docs", response_class=HTMLResponse)
        def docs_not_built() -> str:
            return (
                "<!doctype html><meta charset='utf-8'><title>Documentation — Follow</title>"
                "<body style='font-family: sans-serif; max-width: 40rem; margin: 3rem auto; padding: 0 1rem;'>"
                "<h1>Documentation non construite</h1>"
                "<p>Le site Sphinx n'a pas été construit sur cette installation. Depuis la racine du dépôt :</p>"
                "<pre>pip install \".[docs]\"\nsphinx-build -b html docs docs/_build/html</pre>"
                "<p>puis relancez <code>follow_api start</code> (ou <code>follow_api start --build-docs</code>).</p>"
                "<p><a href='/'>← Retour</a></p></body>"
            )

    if EXAMPLES_DIR.exists():
        app.mount("/examples-gallery", StaticFiles(directory=EXAMPLES_DIR), name="examples-gallery")

    return app
