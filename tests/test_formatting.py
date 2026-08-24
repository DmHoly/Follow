from follow import Quantity, format_value, is_quantity_leaf


def test_plain_scalar_is_stringified():
    assert format_value(42) == "42"
    assert format_value("free text") == "free text"


def test_quantity_with_only_value():
    dumped = Quantity(value=200, unit=None).model_dump(mode="json")
    assert format_value(dumped) == "200"


def test_quantity_with_unit():
    dumped = Quantity(value=200, unit="g").model_dump(mode="json")
    assert format_value(dumped) == "200 g"


def test_quantity_with_uncertainty():
    dumped = Quantity(value=200, unit="g", uncertainty=5).model_dump(mode="json")
    assert format_value(dumped) == "200 g ± 5.0"  # uncertainty is typed float, 5 -> 5.0


def test_quantity_with_note():
    dumped = Quantity(value=200, unit="g", note="mesure a froid").model_dump(mode="json")
    assert format_value(dumped) == "200 g (mesure a froid)"


def test_quantity_with_uncertainty_and_note():
    dumped = Quantity(value=200, unit="g", uncertainty=5, note="mesure a froid").model_dump(mode="json")
    assert format_value(dumped) == "200 g ± 5.0 (mesure a froid)"


def test_is_quantity_leaf_rejects_unrelated_dicts():
    assert is_quantity_leaf({"value": 1, "unit": "g"}) is True
    assert is_quantity_leaf({"value": 1, "extra_unknown_key": True}) is False
    assert is_quantity_leaf({"unit": "g"}) is False  # no "value" key
    assert is_quantity_leaf([1, 2, 3]) is False
    assert is_quantity_leaf("not a dict") is False
