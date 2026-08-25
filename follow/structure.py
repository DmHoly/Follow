from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .errors import StructureTypeError

_REGISTRY: dict[str, type["Structure"]] = {}


class Structure(BaseModel):
    """Base class for the thing an experiment is about: a recipe, a device stack, a device geometry...

    Subclass it to describe a domain (a cake recipe, a MOSFET, a solar cell) with plain, typed,
    nested Pydantic fields. Composition and inheritance both work as usual - a ``SolarModule``
    can hold a list of ``SolarCell``, each holding a ``PNJunction``, and a ``PNJunction`` variant
    can subclass a more generic one to add a few fields. ``Structure`` itself never restricts
    the physics/domain being modelled - genericity comes from walking the fields generically
    (see :mod:`follow.diffing`), not from a fixed schema. Prefer :class:`follow.quantity.Quantity`
    for leaf values so units and uncertainty travel with the number and diffs stay meaningful.

    Define subclasses at module top level. ``registry_key()`` (used to round-trip ``structure``
    back into the right class - see :meth:`resolve`) is derived from ``__module__`` and
    ``__qualname__``; a class defined inside a function or another class gets a qualname like
    ``make_thing.<locals>.MyStructure`` that resolves fine in-process but breaks the CLI's
    ``--structure-type module.Class`` dotted-path import (there's no such importable attribute
    path). Redefining a class under the same module-level name (e.g. re-running a script or a
    notebook cell) also silently replaces its registry entry - fine for the common case, but a
    previously committed experiment whose stored ``structure`` no longer matches the new
    definition's fields will fail to reload with a validation error, not a clear "shape changed"
    message.
    """

    model_config = ConfigDict(extra="forbid")

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        _REGISTRY[cls.registry_key()] = cls

    @classmethod
    def registry_key(cls) -> str:
        return f"{cls.__module__}.{cls.__qualname__}"

    @classmethod
    def resolve(cls, key: str) -> type["Structure"]:
        try:
            return _REGISTRY[key]
        except KeyError as exc:
            raise StructureTypeError(
                f"Unknown structure type {key!r}. Make sure the module defining it "
                "has been imported before loading experiments that use it."
            ) from exc

    @classmethod
    def registered(cls) -> dict[str, type["Structure"]]:
        """Every :class:`Structure` subclass imported so far, keyed by :meth:`registry_key`.

        Used by things that need to enumerate *all* known structure types rather than resolve
        one in particular - e.g. :mod:`follow.api`, to list them for a GUI's "new experiment"
        form. Returns a copy: mutating it does not affect the registry.
        """
        return dict(_REGISTRY)
