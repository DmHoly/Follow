"""A photovoltaics domain, to show a deep composition tree: module -> cell -> junction -> layer.
Diffing and lineage work the same at every depth without Follow knowing anything about PV.
"""

from __future__ import annotations

from follow import Quantity, Structure

from .mosfet import Layer


class PNJunction(Structure):
    n_layer: Layer
    p_layer: Layer
    depletion_width: Quantity


class SolarCell(Structure):
    junction: PNJunction
    anti_reflective_coating: Layer | None = None
    efficiency_estimate: Quantity | None = None


class SolarModule(Structure):
    cells: list[SolarCell]
    encapsulant: str
    frame_material: str
