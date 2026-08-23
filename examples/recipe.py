"""A cooking domain, to show Structure subclassing on something with no physics at all.

A BBQ plan or any other recipe-shaped process would follow the same pattern: a base
Structure with the fields everyone agrees on, specialized by inheritance.
"""

from __future__ import annotations

from follow import Quantity, Structure


class BakeStep(Structure):
    temperature: Quantity
    duration: Quantity


class CakeRecipe(Structure):
    name: str
    ingredients: dict[str, Quantity]
    bake: BakeStep


class ChocolateCakeRecipe(CakeRecipe):
    """A CakeRecipe with a couple of chocolate-specific fields, added purely by inheritance."""

    cocoa_percentage: Quantity
    ganache: bool = False
