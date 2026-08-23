"""A pâtisserie domain used by demos/chocolate_fondant.py: a molten-centre chocolate cake
(fondant au chocolat cœur coulant), optimized from a synthesis of real online recipes rather
than a single source. See that demo script for the full narrative and the recipe sources.
"""

from __future__ import annotations

from follow import Quantity, Structure


class Mold(Structure):
    kind: str  # e.g. "ramequins individuels", "moule à muffins", "moule unique"
    count: int
    buttered_and_floured: bool = True


class MoltenChocolateCake(Structure):
    servings: int
    dark_chocolate: Quantity
    dark_chocolate_cacao_percent: Quantity
    butter: Quantity
    sugar: Quantity
    whole_eggs: int
    egg_yolks: int
    flour: Quantity
    salt: Quantity | None = None
    mold: Mold
    bake_temperature: Quantity
    bake_duration: Quantity
    resting_note: str | None = None  # e.g. chilling the batter, freezing a ganache core
