"""Build a World from NISAR granules.

SME2 hazard evidence per land cell is the stronger of two signals, each scaled
so that 1.0 is a strong change:
  - HH backscatter change between passes, |dB| / 6. Darkening is open water;
    brightening is L-band double bounce from water under vegetation or very wet soil.
  - Soil moisture increase, in m^3/m^3, / 0.2.
Permanent water cells carry no evidence.
A cell is flagged when its evidence reaches 0.5 (a 3 dB change or +0.1 m^3/m^3).
"""

from pathlib import Path

import numpy as np

from proofloop.nisar.sme2 import BBox, read_sme2
from proofloop.world import Grid, HazardLayer, World

STRONG_CHANGE_DB = 6.0
STRONG_WETTING = 0.2
FLAG_THRESHOLD = 0.5
# Cells at least this much permanent water (Gulf, rivers, lakes) are never hazard.
PERMANENT_WATER_FRACTION = 0.5


def build_world_from_sme2(before: Path, after: Path, bbox: BBox) -> World:
    pre = read_sme2(before, bbox)
    post = read_sme2(after, bbox)

    with np.errstate(divide="ignore", invalid="ignore"):
        change_db = 10 * np.log10(post.layers["sigma0_hh"] / pre.layers["sigma0_hh"])
    wetting = post.layers["soil_moisture"] - pre.layers["soil_moisture"]
    evidence = np.fmax(np.abs(change_db) / STRONG_CHANGE_DB, wetting / STRONG_WETTING)
    evidence = np.clip(np.nan_to_num(evidence, nan=0.0), 0.0, 1.0)
    evidence[~(pre.layers["water_fraction"] < PERMANENT_WATER_FRACTION)] = 0.0

    return World(
        grid=Grid(latitude=pre.latitude, longitude=pre.longitude),
        hazard=HazardLayer(flooded=evidence >= FLAG_THRESHOLD, confidence=evidence, method="sme2"),
        population=np.zeros(evidence.shape),
    )
