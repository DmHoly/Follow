"""A DOE (design of experiments) domain: one experiment, one lot, many wafers - each wafer got a
different combination of process parameters, but the lot as a whole is still a single experiment
(one intent, one protocol, one conclusion). See :mod:`follow.doe.batch` for the generic analysis that
makes ``WaferLot.wafers`` useful as a DOE specifically.
"""

from __future__ import annotations

from follow import Quantity, Structure


class Wafer(Structure):
    slot: int
    implant_dose: Quantity
    anneal_temperature: Quantity
    anneal_duration: Quantity


class WaferLot(Structure):
    lot_id: str
    wafer_diameter: Quantity
    process: str
    wafers: list[Wafer]
