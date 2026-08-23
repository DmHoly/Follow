from examples.recipe import BakeStep, CakeRecipe
from follow import Quantity, diff_structures


def _cake(flour_g: float, temperature_c: float) -> CakeRecipe:
    return CakeRecipe(
        name="Vanilla cake",
        ingredients={"flour": Quantity(value=flour_g, unit="g"), "sugar": Quantity(value=150, unit="g")},
        bake=BakeStep(temperature=Quantity(value=temperature_c, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def test_identical_structures_have_no_diff():
    diff = diff_structures(_cake(200, 180), _cake(200, 180))
    assert not diff
    assert len(diff) == 0


def test_changed_leaf_is_reported_as_a_single_quantity_diff():
    diff = diff_structures(_cake(200, 180), _cake(220, 180))
    assert diff.changed_paths == ["ingredients.flour"]
    entry = diff.entries[0]
    assert entry.kind == "changed"
    assert entry.before["value"] == 200
    assert entry.after["value"] == 220


def test_multiple_changes_are_all_reported():
    diff = diff_structures(_cake(200, 180), _cake(220, 200))
    assert set(diff.changed_paths) == {"ingredients.flour", "bake.temperature"}


def test_added_and_removed_ingredients():
    before = _cake(200, 180)
    after = _cake(200, 180)
    after.ingredients["cocoa"] = Quantity(value=50, unit="g")
    del after.ingredients["sugar"]

    diff = diff_structures(before, after)
    kinds = {e.path: e.kind for e in diff.entries}
    assert kinds["ingredients.cocoa"] == "added"
    assert kinds["ingredients.sugar"] == "removed"
