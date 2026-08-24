from examples.chocolate_cake import CakeTrialBatch, ChocolateCake
from follow import Quantity, Repository
from follow.entities import find_entity_mentions


def _cake(trial_id: int = 0, entity_id: str | None = None) -> ChocolateCake:
    return ChocolateCake(
        name="Gateau", trial_id=trial_id, entity_id=entity_id,
        dark_chocolate=Quantity(value=200, unit="g"), cocoa_percent=Quantity(value=64, unit="%"),
        butter=Quantity(value=150, unit="g"), sugar=Quantity(value=180, unit="g"), eggs=4,
        flour=Quantity(value=120, unit="g"), baking_powder=Quantity(value=5, unit="g"),
        bake_temperature=Quantity(value=180, unit="C"), bake_duration=Quantity(value=35, unit="min"),
    )


# -- find_entity_mentions: pure structure-walking --------------------------------------------


def test_find_entity_mentions_returns_empty_when_absent():
    structure = _cake(entity_id="moule-vert").model_dump(mode="json")
    assert find_entity_mentions(structure, "moule-rouge") == []


def test_find_entity_mentions_finds_the_top_level_structure_itself():
    structure = _cake(entity_id="moule-vert").model_dump(mode="json")
    assert find_entity_mentions(structure, "moule-vert") == [""]


def test_find_entity_mentions_finds_a_nested_batch_entry_by_index():
    batch = CakeTrialBatch(batch_id="B1", trials=[_cake(1, "moule-rouge"), _cake(2, "moule-vert")])
    structure = batch.model_dump(mode="json")
    assert find_entity_mentions(structure, "moule-vert") == ["trials[1]"]
    assert find_entity_mentions(structure, "moule-rouge") == ["trials[0]"]


def test_find_entity_mentions_finds_every_matching_path_when_reused_within_one_structure():
    batch = CakeTrialBatch(batch_id="B1", trials=[_cake(1, "moule-vert"), _cake(2, "moule-vert")])
    structure = batch.model_dump(mode="json")
    assert find_entity_mentions(structure, "moule-vert") == ["trials[0]", "trials[1]"]


def test_find_entity_mentions_ignores_none_entity_ids():
    structure = _cake(entity_id=None).model_dump(mode="json")
    assert find_entity_mentions(structure, None) == []


# -- Repository.find_entity: cross-experiment, cross-branch discovery ------------------------


def test_find_entity_returns_nothing_for_an_unmentioned_entity():
    repo = Repository()
    repo.new(branch="main", structure=_cake(entity_id="moule-vert"), title="v1", intent="start").commit()
    assert repo.find_entity("inexistant") == []


def test_find_entity_links_two_unrelated_experiments_by_shared_name_alone():
    # the exact scenario this feature exists for: a batch names one variant "moule-vert", and a
    # later, *unrelated* experiment (different branch, no parent, no reloaded reference) just
    # reuses that name - Follow should still find both.
    repo = Repository()
    batch = repo.new(
        branch="main",
        structure=CakeTrialBatch(batch_id="B1", trials=[_cake(1, "moule-vert"), _cake(2, "moule-rouge")]),
        title="Split moules", intent="comparer 2 moules",
    ).commit()

    followup = repo.new(
        branch="moule-vert-nutella",
        structure=_cake(1, "moule-vert").model_copy(update={"name": "Gateau + nutella"}),
        title="Injection Nutella", intent="ameliorer le moule vert",
    ).commit()

    assert [exp.id for exp in repo.find_entity("moule-vert")] == [batch.id, followup.id]
    assert [exp.id for exp in repo.find_entity("moule-rouge")] == [batch.id]


def test_find_entity_orders_matches_oldest_first_regardless_of_commit_order():
    repo = Repository()
    first = repo.new(branch="a", structure=_cake(entity_id="wafer-1"), title="first", intent="i").commit()
    second = repo.new(branch="b", structure=_cake(entity_id="wafer-1"), title="second", intent="i").commit()

    matches = repo.find_entity("wafer-1")
    assert [exp.id for exp in matches] == [first.id, second.id]


def test_find_entity_works_through_derive_as_well_as_new():
    repo = Repository()
    baseline = repo.new(branch="main", structure=_cake(entity_id="wafer-A3"), title="v1", intent="start").commit()
    variant = repo.derive(baseline.id, title="v2", intent="tweak").commit()

    assert [exp.id for exp in repo.find_entity("wafer-A3")] == [baseline.id, variant.id]
