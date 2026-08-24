"""Generate structural variants of a reference Structure for a DOE, instead of hand-writing every
combination (see how demos/wafer_doe.py currently builds its 25-wafer lot with a nested loop).

Two halves:

- Value generators (:func:`lin`, :func:`log`, :func:`arange`) - thin numpy wrappers that also
  know how to wrap into :class:`~follow.quantity.Quantity` when a unit is given, since most real
  factors are quantities, not bare floats.
- Design builders (:func:`sweep`, :func:`full_factorial`, :func:`latin_hypercube`) - each takes a
  single reference instance (already valid, already the baseline you'd otherwise copy by hand)
  and a spec per varying field, and returns the list of variants ready to drop straight into a
  ``Structure``'s list field and commit as one experiment.

:func:`check_identifiability` is the other half of "je veux pas faire un split idiot": after
building a design (by any of the above, or by hand), it flags any two factors that varied
together closely enough that a regression could not tell their individual effects apart -
the textbook mistake is a "diagonal" sweep where two parameters are both stepped up together
instead of crossed.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Sequence, TypeVar

import numpy as np
from pydantic import BaseModel

from .errors import DesignError
from .quantity import Quantity

T = TypeVar("T", bound=BaseModel)

# -- value generators ----------------------------------------------------------------------


def _wrap(values: list[float], unit: str | None) -> list[Any]:
    return values if unit is None else [Quantity(value=v, unit=unit) for v in values]


def lin(start: float, stop: float, n: int, *, unit: str | None = None) -> list[Any]:
    """``n`` evenly spaced values from ``start`` to ``stop`` (inclusive) - ``numpy.linspace``."""
    return _wrap(np.linspace(start, stop, n).tolist(), unit)


def log(start: float, stop: float, n: int, *, unit: str | None = None) -> list[Any]:
    """``n`` log-spaced values from ``start`` to ``stop`` (inclusive, both > 0) -
    ``numpy.geomspace``. Use this instead of :func:`lin` when a factor's *effect* is expected to
    scale multiplicatively rather than additively (concentrations, doses, frequencies...).
    """
    return _wrap(np.geomspace(start, stop, n).tolist(), unit)


def arange(start: float, stop: float, step: float, *, unit: str | None = None) -> list[Any]:
    """Values from ``start`` up to (excluding) ``stop`` in steps of ``step`` - ``numpy.arange``,
    for when you know the step size you want rather than how many points.
    """
    return _wrap(np.arange(start, stop, step).tolist(), unit)


# -- design builders ------------------------------------------------------------------------


def _check_fields(reference: BaseModel, names: Sequence[str], *, what: str = "facteur") -> None:
    """Reject a field name the reference doesn't actually have, before it silently does nothing.

    ``model_copy(update=...)`` writes whatever it is given without validating, bypassing
    ``Structure``'s ``extra="forbid"`` - so a typo'd factor name used to produce a design where
    the intended field never varied at all, with no error anywhere (and
    :func:`check_identifiability` then cheerfully reporting the empty design as clean).
    """
    known = type(reference).model_fields
    unknown = sorted(name for name in names if name not in known)
    if unknown:
        raise DesignError(
            f"{what}(s) inconnu(s) de {type(reference).__name__}: {unknown} - "
            f"champs disponibles: {sorted(known)}"
        )


def _variant(reference: T, updates: dict[str, Any]) -> T:
    """One variant of ``reference`` with ``updates`` applied - validated, unlike ``model_copy``.

    Re-validating through the model is what turns "a float where a Quantity was expected" into an
    error here, instead of a repository entry that only fails much later, at reload time.
    """
    _check_fields(reference, list(updates))
    return type(reference).model_validate({**reference.model_dump(), **updates})


def _number(variants: list[T], id_field: str | None) -> list[T]:
    if id_field is None:
        return variants
    if variants:
        _check_fields(variants[0], [id_field], what="id_field")
    return [_variant(v, {id_field: i + 1}) for i, v in enumerate(variants)]


def sweep(reference: T, field: str, values: Sequence[Any], *, id_field: str | None = None) -> list[T]:
    """One factor at a time: ``field`` takes each value in ``values``, everything else stays
    exactly as ``reference``. Always statistically identifiable - there is only one thing
    changing, so nothing to confound it with.

    Raises :class:`ValueError` if ``field`` isn't a field of ``reference`` (a typo would otherwise
    produce N identical variants and a design that varies nothing), and a
    :class:`pydantic.ValidationError` if a value doesn't fit that field's type.
    """
    return _number([_variant(reference, {field: v}) for v in values], id_field)


def full_factorial(reference: T, *, id_field: str | None = None, **factors: Sequence[Any]) -> list[T]:
    """Every combination of every factor's values, fully crossed - N factors, product of their
    lengths entities (5 doses x 5 temperatures = 25). A full factorial is always identifiable:
    every main effect and every interaction can be estimated independently of every other,
    by construction.

    Every factor name must be a field of ``reference`` - an unknown one raises rather than
    quietly producing a design in which that factor never varied.
    """
    names = list(factors)
    _check_fields(reference, names)
    grids = [factors[name] for name in names]
    variants = [_variant(reference, dict(zip(names, combo))) for combo in itertools.product(*grids)]
    return _number(variants, id_field)


def latin_hypercube(
    reference: T, n: int, *, seed: int | None = None, id_field: str | None = None, **factor_ranges: tuple
) -> list[T]:
    """``n`` random combinations, stratified so each factor's range is evenly covered even though
    the combinations themselves are randomized - a screening design for when a full factorial
    would need too many runs, or when you don't yet know which factors matter. Pass each factor
    as ``(low, high)`` or ``(low, high, unit)``.

    Every factor name must be a field of ``reference`` - an unknown one raises rather than
    quietly producing a design in which that factor never varied.
    """
    rng = np.random.default_rng(seed)
    names = list(factor_ranges)
    _check_fields(reference, names)
    cut = np.linspace(0, 1, n + 1)
    samples = np.empty((n, len(names)))
    for j in range(len(names)):
        jitter = rng.uniform(size=n)
        points = cut[:n] + jitter * (cut[1:] - cut[:n])
        rng.shuffle(points)
        samples[:, j] = points

    variants = []
    for row in samples:
        updates: dict[str, Any] = {}
        for j, name in enumerate(names):
            spec = factor_ranges[name]
            low, high = spec[0], spec[1]
            unit = spec[2] if len(spec) > 2 else None
            value = low + row[j] * (high - low)
            updates[name] = Quantity(value=value, unit=unit) if unit else value
        variants.append(_variant(reference, updates))
    return _number(variants, id_field)


# -- fractional factorial + alias structure --------------------------------------------------


def _alias_group(words: list[frozenset[str]]) -> set[frozenset[str]]:
    """The group of "words" in a defining relation, generated by symmetric difference (mod-2
    addition of exponents - squaring a factor removes it, e.g. A*A*B = B) closure over the given
    generator words.
    """
    group = {frozenset()}
    for word in words:
        group |= {g ^ word for g in group}
    return group


def _label(effect: frozenset[str]) -> str:
    return ":".join(sorted(effect)) if effect else "I"


def alias_structure(factors: Sequence[str], generators: dict[str, Sequence[str]], *, order: int = 2) -> dict[str, list[str]]:
    """The alias structure a set of ``generators`` induces on ``factors``, computed from the
    design's defining relation - independently of :func:`fractional_factorial`, so a candidate
    design can be checked *before* generating a single variant.

    ``generators`` maps each generated factor's name to the base factors whose product defines
    its sign (e.g. ``{"D": ["A", "B", "C"]}`` for the classic 2^(4-1) resolution IV design
    ``D = ABC``). For every main effect and, up to ``order``, every interaction among
    ``factors``, the result lists every other effect it is statistically indistinguishable from
    - an empty list would mean the effect is aliased with nothing (impossible for order >= 1
    once any generator exists, since every effect is at least aliased with itself under the
    trivial word - callers only care about the *other* entries).
    """
    words = [frozenset(word) | {name} for name, word in generators.items()]
    group = _alias_group(words)
    group.discard(frozenset())

    effects = [frozenset(c) for r in range(1, order + 1) for c in itertools.combinations(factors, r)]
    result = {}
    for effect in effects:
        aliases = sorted((effect ^ word for word in group), key=lambda s: (len(s), sorted(s)))
        result[_label(effect)] = [_label(a) for a in aliases]
    return result


@dataclass(frozen=True)
class FractionalFactorial:
    """Result of :func:`fractional_factorial`: the generated variants, the design's resolution
    (the length of the shortest word in its defining relation - III means some main effect is
    aliased with a 2-factor interaction, IV means only with 3-factor-or-higher interactions, and
    so on - ``None`` if ``generators`` was empty, i.e. this was really a full factorial), and the
    full alias structure (see :func:`alias_structure`) for every main effect and 2-factor
    interaction.
    """

    variants: list
    resolution: int | None
    aliases: dict[str, list[str]]


def fractional_factorial(
    reference: T,
    factors: dict[str, tuple],
    generators: dict[str, Sequence[str]],
    *,
    id_field: str | None = None,
) -> FractionalFactorial:
    """A 2-level fractional factorial: ``factors`` gives every factor's low/high (optionally with
    a unit, as ``(low, high)`` or ``(low, high, unit)``). Factors NOT listed in ``generators`` are
    the design's base factors and get a full 2^k factorial in coded units; each factor listed in
    ``generators`` instead takes its sign from the product of the named base factors' signs - e.g.
    ``generators={"D": ["A", "B", "C"]}`` runs ``D`` at its high level exactly when A*B*C's coded
    product is +1. This cuts the run count a full factorial would need (2^k instead of
    2^(k+len(generators))), at the cost of aliasing some effects together - which effects,
    exactly, is right there in the returned :class:`FractionalFactorial`, not something you find
    out after the fact from confusing results.

    Every factor name must be a field of ``reference`` - an unknown one raises rather than
    quietly producing a design in which that factor never varied.
    """
    _check_fields(reference, list(factors))
    base_names = [name for name in factors if name not in generators]
    if not base_names:
        raise DesignError("au moins un facteur doit être un facteur de base (absent de `generators`)")
    for name, word in generators.items():
        unknown = [w for w in word if w not in factors]
        if unknown:
            raise DesignError(f"générateur de {name!r} référence des facteurs inconnus: {unknown}")

    variants: list[T] = []
    for combo in itertools.product([-1, 1], repeat=len(base_names)):
        signs = dict(zip(base_names, combo))
        for name, word in generators.items():
            sign = 1
            for w in word:
                sign *= signs[w]
            signs[name] = sign
        updates: dict[str, Any] = {}
        for name, sign in signs.items():
            spec = factors[name]
            low, high = spec[0], spec[1]
            unit = spec[2] if len(spec) > 2 else None
            value = high if sign == 1 else low
            updates[name] = Quantity(value=value, unit=unit) if unit else value
        variants.append(_variant(reference, updates))
    variants = _number(variants, id_field)

    words = [frozenset(word) | {name} for name, word in generators.items()]
    group = _alias_group(words)
    group.discard(frozenset())
    resolution = min((len(word) for word in group), default=None)

    return FractionalFactorial(variants=variants, resolution=resolution, aliases=alias_structure(list(factors), generators))


# -- identifiability check -------------------------------------------------------------------


def check_identifiability(variants: Sequence[BaseModel], factors: Sequence[str], *, threshold: float = 0.95) -> list[tuple[str, str, float]]:
    """After building a design (by any of the functions above, or by hand), check whether any two
    factors varied together closely enough that their individual effects could not be told apart
    statistically - the textbook mistake being a "diagonal" sweep where two parameters are both
    stepped up together instead of crossed. Returns every factor pair whose correlation across
    the design exceeds ``threshold`` in absolute value, worst first; an empty list means every
    factor varies independently enough to have its own effect estimated.

    This is a correlation check on the design itself, before any measurement - it has nothing to
    do with the experiment's outcome, only with whether the *plan* could ever separate these two
    factors' effects no matter what gets measured.

    Every name in ``factors`` must be a field of the variants being checked. Silently skipping an
    unknown one would make this function answer "nothing is confounded" about a factor it never
    looked at - the most misleading answer it could give, since the whole point is to be trusted
    when it says a design is clean.
    """
    if not variants:
        return []
    _check_fields(variants[0], factors)
    columns: dict[str, np.ndarray] = {}
    for name in factors:
        values = []
        for variant in variants:
            value = getattr(variant, name)
            values.append(value.value if isinstance(value, Quantity) else value)
        columns[name] = np.asarray(values, dtype=float)

    flagged = []
    for a, b in itertools.combinations(factors, 2):
        if np.std(columns[a]) == 0 or np.std(columns[b]) == 0:
            continue  # a constant column can't be confounded with anything
        corr = float(np.corrcoef(columns[a], columns[b])[0, 1])
        if abs(corr) >= threshold:
            flagged.append((a, b, corr))
    return sorted(flagged, key=lambda t: -abs(t[2]))
