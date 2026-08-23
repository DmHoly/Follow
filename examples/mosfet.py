"""A semiconductor-device domain, to show nested composition and structural evolution
(planar MOSFET -> FinFET) purely via Structure inheritance - no changes needed in Follow.
"""

from __future__ import annotations

from follow import Quantity, Structure


class Layer(Structure):
    material: str
    thickness: Quantity
    doping: Quantity | None = None


class MOSFETStructure(Structure):
    gate_length: Quantity
    gate_oxide: Layer
    channel_doping: Quantity
    source: Layer
    drain: Layer


class FinFETStructure(MOSFETStructure):
    """The same planar fields, plus the geometry that makes it a FinFET instead."""

    fin_height: Quantity
    fin_width: Quantity
    number_of_fins: int
