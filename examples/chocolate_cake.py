"""A chocolate cake domain, built specifically to carry every factor as a flat top-level field
(unlike examples/recipe.py's dict-based ``ingredients``) - that's what lets follow.doe.design's
model_copy(update={field: value}) mechanism target each one directly, which is what a DOE split
needs. ``ChocolateCake`` works both as a single recipe (the baseline, or a validated final
recipe) and as one trial inside a ``CakeTrialBatch`` - the same shape either way, so a whole
study can move from "one recipe" to "N variants of that recipe" and back without redefining
anything.
"""

from __future__ import annotations

from follow import Quantity, Structure


class ChocolateCake(Structure):
    name: str
    trial_id: int = 0  # only meaningful inside a CakeTrialBatch - identifies which trial this is
    entity_id: str | None = None  # a name for the physical cake, e.g. "moule-vert" - see follow.paths.entities
    dark_chocolate: Quantity
    cocoa_percent: Quantity
    butter: Quantity
    sugar: Quantity
    eggs: int
    flour: Quantity
    baking_powder: Quantity
    bake_temperature: Quantity
    bake_duration: Quantity
    topping: str | None = None  # a modification made to one specific physical cake after baking


class CakeTrialBatch(Structure):
    """A DOE batch: several ``ChocolateCake`` trials, tracked as a single experiment. See
    follow.doe.batch/follow.doe.design - a batch is still one intent, one protocol, one conclusion, even
    though its structure holds many variants.
    """

    batch_id: str
    trials: list[ChocolateCake]
