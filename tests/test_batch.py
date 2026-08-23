import pytest

from examples.wafer_doe import Wafer, WaferLot
from follow import BatchFactor, BatchVariation, Quantity, analyze_batch


def _wafer(slot: int, dose: float, temp: float, duration: float = 30) -> Wafer:
    return Wafer(
        slot=slot,
        implant_dose=Quantity(value=dose, unit="1e14 cm^-2"),
        anneal_temperature=Quantity(value=temp, unit="C"),
        anneal_duration=Quantity(value=duration, unit="min"),
    )


def test_empty_batch_is_trivially_uniform():
    result = analyze_batch([])
    assert result == BatchVariation(entity_count=0)
    assert result.is_uniform is True


def test_single_entity_batch_is_uniform_with_everything_constant():
    result = analyze_batch([_wafer(1, 6, 1000)])
    assert result.entity_count == 1
    assert result.is_uniform is True
    assert result.varying == []
    assert result.constant["slot"] == 1
    assert result.constant["implant_dose"]["value"] == 6


def test_identical_entities_are_uniform_even_with_multiple_of_them():
    wafers = [_wafer(1, 6, 1000), _wafer(1, 6, 1000), _wafer(1, 6, 1000)]
    result = analyze_batch(wafers)
    assert result.entity_count == 3
    assert result.is_uniform is True
    assert result.constant["implant_dose"]["value"] == 6


def test_varying_field_is_split_out_with_one_value_per_entity_in_order():
    wafers = [_wafer(1, 2, 1000), _wafer(2, 4, 1000), _wafer(3, 6, 1000)]
    result = analyze_batch(wafers)
    assert result.entity_count == 3
    assert result.is_uniform is False
    assert set(result.constant) == {"anneal_temperature", "anneal_duration"}

    by_path = {f.path: f for f in result.varying}
    assert set(by_path) == {"slot", "implant_dose"}
    assert by_path["slot"] == BatchFactor(path="slot", values=[1, 2, 3])
    assert [v["value"] for v in by_path["implant_dose"].values] == [2, 4, 6]


def test_ignore_excludes_identity_fields_from_both_constant_and_varying():
    # "slot" differs on every wafer by construction - without `ignore` a batch that is otherwise
    # uniform (same dose/temp/duration everywhere) would never report is_uniform=True.
    wafers = [_wafer(1, 6, 1000), _wafer(2, 6, 1000), _wafer(3, 6, 1000)]
    result = analyze_batch(wafers, ignore=["slot"])
    assert result.is_uniform is True
    assert "slot" not in result.constant
    assert all(f.path != "slot" for f in result.varying)


def test_analyze_batch_accepts_plain_dumped_dicts_not_just_models():
    dumps = [_wafer(1, 2, 1000).model_dump(mode="json"), _wafer(2, 4, 1000).model_dump(mode="json")]
    result = analyze_batch(dumps)
    assert result.entity_count == 2
    assert any(f.path == "implant_dose" for f in result.varying)


def test_heterogeneous_entities_raise_instead_of_silently_comparing_wrong_things():
    a = {"x": 1, "nested": {"y": 2}}
    b = {"x": 1}  # missing "nested" entirely
    with pytest.raises(KeyError):
        analyze_batch([a, b])


def test_leaf_paths_walk_into_nested_list_valued_fields():
    # a field that is itself a list (not a Quantity, not a dict) - e.g. a wafer with several
    # measurement tags - must be walked index by index like diffing.py does, not treated as a
    # single opaque leaf.
    a = {"tags": ["edge", "center"]}
    b = {"tags": ["edge", "flat"]}
    result = analyze_batch([a, b])
    assert result.constant == {"tags[0]": "edge"}
    assert [f.path for f in result.varying] == ["tags[1]"]
    assert result.varying[0].values == ["center", "flat"]


def test_nested_structure_list_field_is_walked_via_wafer_lot():
    lot = WaferLot(
        lot_id="LOT-A",
        wafer_diameter=Quantity(value=200, unit="mm"),
        process="implant+anneal",
        wafers=[_wafer(1, 2, 900), _wafer(2, 2, 950)],
    )
    result = analyze_batch(lot.wafers, ignore=["slot"])
    assert result.entity_count == 2
    assert result.constant["implant_dose"]["value"] == 2
    assert any(f.path == "anneal_temperature" for f in result.varying)
