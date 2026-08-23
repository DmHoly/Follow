from __future__ import annotations

from pydantic import BaseModel, ConfigDict

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
            raise KeyError(
                f"Unknown structure type {key!r}. Make sure the module defining it "
                "has been imported before loading experiments that use it."
            ) from exc
