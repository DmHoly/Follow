import pytest

from examples.wafer_doe import Wafer
from follow import Quantity
from follow.design import (
    alias_structure,
    arange,
    check_identifiability,
    fractional_factorial,
    full_factorial,
    latin_hypercube,
    lin,
    log,
    sweep,
)


def _reference() -> Wafer:
    return Wafer(
        slot=0,
        implant_dose=Quantity(value=0, unit="1e14 cm^-2"),
        anneal_temperature=Quantity(value=0, unit="C"),
        anneal_duration=Quantity(value=30, unit="min"),
    )


def test_lin_log_arange_generate_expected_values():
    assert lin(0, 10, 5) == [0.0, 2.5, 5.0, 7.5, 10.0]
    assert log(1, 100, 3) == pytest.approx([1.0, 10.0, 100.0])
    assert arange(0, 10, 5) == [0.0, 5.0]


def test_lin_wraps_into_quantity_when_unit_is_given():
    values = lin(900, 1100, 3, unit="C")
    assert [v.value for v in values] == [900.0, 1000.0, 1100.0]
    assert all(v.unit == "C" for v in values)


def test_sweep_varies_one_field_only():
    variants = sweep(_reference(), "implant_dose", lin(2, 10, 3, unit="1e14 cm^-2"), id_field="slot")
    assert len(variants) == 3
    assert [v.slot for v in variants] == [1, 2, 3]
    assert [v.implant_dose.value for v in variants] == [2.0, 6.0, 10.0]
    # everything else stays identical to the reference
    assert all(v.anneal_temperature == _reference().anneal_temperature for v in variants)


def test_full_factorial_crosses_every_combination():
    lot = full_factorial(
        _reference(),
        id_field="slot",
        implant_dose=lin(2, 10, 5, unit="1e14 cm^-2"),
        anneal_temperature=lin(900, 1100, 5, unit="C"),
    )
    assert len(lot) == 25
    assert lot[0].implant_dose.value == 2.0 and lot[0].anneal_temperature.value == 900.0
    assert lot[-1].implant_dose.value == 10.0 and lot[-1].anneal_temperature.value == 1100.0
    assert [w.slot for w in lot] == list(range(1, 26))


def test_full_factorial_is_always_identifiable():
    lot = full_factorial(
        _reference(),
        implant_dose=lin(2, 10, 5, unit="1e14 cm^-2"),
        anneal_temperature=lin(900, 1100, 5, unit="C"),
    )
    assert check_identifiability(lot, ["implant_dose", "anneal_temperature"]) == []


def test_check_identifiability_flags_a_diagonal_sweep():
    # the classic mistake: two factors both stepped up together instead of crossed
    variants = [
        _reference().model_copy(
            update={"implant_dose": Quantity(value=d, unit="1e14 cm^-2"), "anneal_temperature": Quantity(value=t, unit="C")}
        )
        for d, t in zip([2, 4, 6, 8, 10], [900, 950, 1000, 1050, 1100])
    ]
    flagged = check_identifiability(variants, ["implant_dose", "anneal_temperature"])
    assert len(flagged) == 1
    a, b, corr = flagged[0]
    assert {a, b} == {"implant_dose", "anneal_temperature"}
    assert corr == pytest.approx(1.0)


def test_check_identifiability_ignores_a_constant_column():
    variants = full_factorial(_reference(), implant_dose=lin(2, 10, 3, unit="1e14 cm^-2"))
    # anneal_temperature never varies here - can't be "confounded" with anything
    assert check_identifiability(variants, ["implant_dose", "anneal_temperature"]) == []


def test_latin_hypercube_produces_n_variants_within_range():
    variants = latin_hypercube(
        _reference(), 12, seed=0, id_field="slot",
        implant_dose=(2, 10, "1e14 cm^-2"), anneal_temperature=(900, 1100, "C"),
    )
    assert len(variants) == 12
    assert [w.slot for w in variants] == list(range(1, 13))
    for w in variants:
        assert 2 <= w.implant_dose.value <= 10
        assert 900 <= w.anneal_temperature.value <= 1100


def test_latin_hypercube_is_reproducible_with_a_seed():
    a = latin_hypercube(_reference(), 5, seed=42, implant_dose=(2, 10, "1e14 cm^-2"))
    b = latin_hypercube(_reference(), 5, seed=42, implant_dose=(2, 10, "1e14 cm^-2"))
    assert [v.implant_dose.value for v in a] == [v.implant_dose.value for v in b]


def test_alias_structure_resolution_iii_matches_textbook_2_to_the_3_minus_1():
    aliases = alias_structure(["A", "B", "C"], generators={"C": ["A", "B"]})
    assert aliases["A"] == ["B:C"]
    assert aliases["B"] == ["A:C"]
    assert aliases["C"] == ["A:B"]
    assert aliases["A:B"] == ["C"]


def test_alias_structure_resolution_iv_matches_textbook_2_to_the_4_minus_1():
    aliases = alias_structure(["A", "B", "C", "D"], generators={"D": ["A", "B", "C"]})
    # main effects alias with the 3-factor interaction of the other three
    assert aliases["A"] == ["B:C:D"]
    assert aliases["D"] == ["A:B:C"]
    # 2-factor interactions alias with their complementary pair (AB<->CD, AC<->BD, AD<->BC)
    assert aliases["A:B"] == ["C:D"]
    assert aliases["A:C"] == ["B:D"]
    assert aliases["A:D"] == ["B:C"]


def test_fractional_factorial_generates_correct_run_count_and_resolution():
    result = fractional_factorial(
        _reference(),
        factors={
            "implant_dose": (2, 10, "1e14 cm^-2"),
            "anneal_temperature": (900, 1100, "C"),
            "anneal_duration": (20, 40, "min"),
        },
        generators={"anneal_duration": ["implant_dose", "anneal_temperature"]},
        id_field="slot",
    )
    assert len(result.variants) == 4  # 2^(3-1)
    assert result.resolution == 3
    assert result.aliases["implant_dose"] == ["anneal_duration:anneal_temperature"]
    # every variant only ever takes the low or high level of each factor
    for w in result.variants:
        assert w.implant_dose.value in (2, 10)
        assert w.anneal_temperature.value in (900, 1100)
        assert w.anneal_duration.value in (20, 40)


def test_fractional_factorial_full_factorial_has_no_resolution_when_no_generators():
    result = fractional_factorial(
        _reference(),
        factors={"implant_dose": (2, 10, "1e14 cm^-2"), "anneal_temperature": (900, 1100, "C")},
        generators={},
    )
    assert len(result.variants) == 4  # 2^2, a plain full factorial
    assert result.resolution is None
    assert result.aliases["implant_dose"] == []  # aliased with nothing


def test_fractional_factorial_rejects_a_generator_referencing_an_unknown_factor():
    with pytest.raises(ValueError, match="inconnus"):
        fractional_factorial(
            _reference(),
            factors={"implant_dose": (2, 10, "1e14 cm^-2"), "anneal_temperature": (900, 1100, "C")},
            generators={"anneal_temperature": ["implant_dose", "typo_factor"]},
        )


def test_fractional_factorial_requires_at_least_one_base_factor():
    with pytest.raises(ValueError, match="base"):
        fractional_factorial(
            _reference(),
            factors={"implant_dose": (2, 10, "1e14 cm^-2")},
            generators={"implant_dose": []},
        )
