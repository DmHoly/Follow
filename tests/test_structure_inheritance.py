import pytest
from pydantic import ValidationError

from examples.mosfet import FinFETStructure, Layer, MOSFETStructure
from examples.recipe import ChocolateCakeRecipe
from examples.solar_cell import PNJunction, SolarCell, SolarModule
from follow import Quantity, Structure


def test_domain_subclass_registers_itself():
    assert Structure.resolve(MOSFETStructure.registry_key()) is MOSFETStructure


def test_inheritance_adds_fields_without_touching_the_base():
    finfet = FinFETStructure(
        gate_length=Quantity(value=20, unit="nm"),
        gate_oxide=Layer(material="HfO2", thickness=Quantity(value=2, unit="nm")),
        channel_doping=Quantity(value=1e17, unit="cm^-3"),
        source=Layer(material="Si:P", thickness=Quantity(value=50, unit="nm")),
        drain=Layer(material="Si:P", thickness=Quantity(value=50, unit="nm")),
        fin_height=Quantity(value=40, unit="nm"),
        fin_width=Quantity(value=8, unit="nm"),
        number_of_fins=3,
    )
    assert isinstance(finfet, MOSFETStructure)
    assert finfet.number_of_fins == 3


def test_deep_composition_round_trips_through_json():
    module = SolarModule(
        cells=[
            SolarCell(
                junction=PNJunction(
                    n_layer=Layer(material="Si:P", thickness=Quantity(value=200, unit="nm")),
                    p_layer=Layer(material="Si:B", thickness=Quantity(value=180, unit="um")),
                    depletion_width=Quantity(value=0.5, unit="um"),
                ),
            )
        ],
        encapsulant="EVA",
        frame_material="aluminium",
    )
    dumped = module.model_dump(mode="json")
    restored = SolarModule.model_validate(dumped)
    assert restored == module


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        ChocolateCakeRecipe(
            name="Devil's food",
            ingredients={"flour": Quantity(value=200, unit="g")},
            bake={"temperature": {"value": 180, "unit": "C"}, "duration": {"value": 35, "unit": "min"}},
            cocoa_percentage=Quantity(value=70, unit="%"),
            unexpected_field="nope",
        )
