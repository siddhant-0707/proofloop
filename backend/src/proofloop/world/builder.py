"""Build a World from NISAR granules.

GCOV (10 to 20 m) is the primary hazard source and SME2 (200 m) the fallback.

GCOV hazard evidence per land cell comes from the HH backscatter change between
passes, after averaging pixels into cells of about 60 m to suppress speckle:
  - Open water: darkening, |dB| / 6, only where the after pass is dark enough to be water.
  - Under canopy: L-band double bounce from water under vegetation, which is how flooding
    under the Big Bend's tree canopy shows up. Only cells already bright enough to be
    vegetated count. Rain wets soil across the whole scene and brightens it by a dB or two,
    so brightening counts only beyond the median land change, (dB - median) / 6.

SME2 hazard evidence per land cell is the stronger of two signals, each scaled
so that 1.0 is a strong change:
  - HH backscatter change between passes, |dB| / 6.
  - Soil moisture increase, in m^3/m^3, / 0.2.

Permanent water cells carry no evidence.
A cell is flagged when its evidence reaches 0.5 (a 3 dB change or +0.1 m^3/m^3).
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyproj import Transformer

from proofloop.nisar.gcov import GcovGrid, read_gcov
from proofloop.nisar.sme2 import BBox, Sme2Grid, read_sme2
from proofloop.world import FloodKind, Grid, HazardLayer, World

STRONG_CHANGE_DB = 6.0
STRONG_WETTING = 0.2
FLAG_THRESHOLD = 0.5
# Cells at least this much permanent water (Gulf, rivers, lakes) are never hazard.
PERMANENT_WATER_FRACTION = 0.5
# GCOV cells this dark in HH before the storm were already open water. On frame 16 at 60 m,
# permanent water has a median of -18.6 dB and land a 1st percentile of -16.3 dB.
ALREADY_WATER_DB = -17.0
# New open water must be at least this dark in HH after the storm.
OPEN_WATER_DB = -15.0
# Double bounce needs vegetation, already this bright in HH before the storm. Darker cells
# that brighten are mostly bare fields wetted or planted (the center pivots east of Cross City).
CANOPY_MIN_DB = -12.0
GCOV_CELL_M = 60.0
# How far people can travel to a shelter, used to size World.reach_cells.
TRAVEL_REACH_M = 5_000.0
_METERS_PER_DEGREE = 111_320.0


@dataclass(frozen=True)
class GranulePair:
    before: Path
    after: Path

    def exist(self) -> bool:
        return self.before.exists() and self.after.exists()


def build_world(bbox: BBox, sme2: GranulePair, gcov: GranulePair | None = None) -> World:
    """Use GCOV when both granules are present, otherwise fall back to SME2."""
    if gcov is not None and gcov.exist():
        return build_world_from_gcov(gcov.before, gcov.after, bbox, permanent_water=sme2.before)
    return build_world_from_sme2(sme2.before, sme2.after, bbox)


def build_world_from_gcov(
    before: Path, after: Path, bbox: BBox, permanent_water: Path, cell_m: float = GCOV_CELL_M
) -> World:
    """`permanent_water` is an SME2 granule whose water fraction masks the Gulf and rivers."""
    grid = _latlon_grid(bbox, cell_m)
    pre_hh = _resample(read_gcov(before, bbox, cell_m, layers=("hh",)), "hh", grid, cell_m)
    post_hh = _resample(read_gcov(after, bbox, cell_m, layers=("hh",)), "hh", grid, cell_m)
    water_fraction = _sample_sme2(read_sme2(permanent_water), "water_fraction", grid)

    with np.errstate(divide="ignore", invalid="ignore"):
        change_db = 10 * np.log10(post_hh / pre_hh)
        before_db = 10 * np.log10(pre_hh)
        after_db = 10 * np.log10(post_hh)
    land = (water_fraction < PERMANENT_WATER_FRACTION) & (before_db > ALREADY_WATER_DB)
    measured = land & np.isfinite(change_db)
    baseline_db = max(0.0, float(np.median(change_db[measured]))) if measured.any() else 0.0

    open_water = np.where(after_db <= OPEN_WATER_DB, -change_db, 0.0)
    canopy = np.where(before_db >= CANOPY_MIN_DB, change_db - baseline_db, 0.0)
    evidence = np.nan_to_num(np.fmax(open_water, canopy) / STRONG_CHANGE_DB, nan=0.0)
    evidence = np.where(land, np.clip(evidence, 0.0, 1.0), 0.0)

    flooded = evidence >= FLAG_THRESHOLD
    kind = np.where(open_water > canopy, FloodKind.OPEN_WATER, FloodKind.UNDER_CANOPY)
    kind = np.where(flooded, kind, FloodKind.NONE).astype(np.uint8)
    return World(
        grid=grid,
        hazard=HazardLayer(flooded=flooded, confidence=evidence, method="gcov", kind=kind),
        population=np.zeros(evidence.shape),
        reach_cells=round(TRAVEL_REACH_M / cell_m),
    )


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


def _latlon_grid(bbox: BBox, cell_m: float) -> Grid:
    """Cells of about `cell_m` meters that exactly tile the bbox."""
    mid_lat = np.radians((bbox.south + bbox.north) / 2)
    rows = max(1, round((bbox.north - bbox.south) * _METERS_PER_DEGREE / cell_m))
    cols = max(1, round((bbox.east - bbox.west) * _METERS_PER_DEGREE * np.cos(mid_lat) / cell_m))
    lat = bbox.north - (np.arange(rows) + 0.5) * (bbox.north - bbox.south) / rows
    lon = bbox.west + (np.arange(cols) + 0.5) * (bbox.east - bbox.west) / cols
    return Grid(latitude=lat, longitude=lon)


def _resample(gcov: GcovGrid, layer: str, grid: Grid, cell_m: float) -> np.ndarray:
    """Average GCOV pixels into blocks of about `cell_m`, then sample them at the grid's cells."""
    looks = max(1, round(cell_m / gcov.spacing)) if gcov.spacing else 1
    power = _multilook(gcov.layers[layer], looks)
    block_m = gcov.spacing * looks
    x0 = gcov.x[0] + (looks - 1) * gcov.spacing / 2
    y0 = gcov.y[0] - (looks - 1) * gcov.spacing / 2

    lon, lat = np.meshgrid(grid.longitude, grid.latitude)
    x, y = Transformer.from_crs(4326, gcov.epsg, always_xy=True).transform(lon, lat)
    col = np.rint((x - x0) / block_m).astype(np.int64)
    row = np.rint((y0 - y) / block_m).astype(np.int64)
    inside = (row >= 0) & (row < power.shape[0]) & (col >= 0) & (col < power.shape[1])
    out = np.full(grid.shape, np.nan)
    out[inside] = power[row[inside], col[inside]]
    return out


def _multilook(power: np.ndarray, looks: int) -> np.ndarray:
    """Mean of each looks x looks block, NaN unless at least half the block is valid."""
    rows, cols = (power.shape[0] // looks) * looks, (power.shape[1] // looks) * looks
    blocks = power[:rows, :cols].reshape(rows // looks, looks, cols // looks, looks)
    valid = ~np.isnan(blocks)
    count = valid.sum(axis=(1, 3))
    total = np.where(valid, blocks, np.float32(0)).sum(axis=(1, 3), dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(count * 2 >= looks * looks, total / count, np.nan)


def _sample_sme2(sme2: Sme2Grid, layer: str, grid: Grid) -> np.ndarray:
    """The nearest SME2 cell's value at each grid cell."""
    rows = np.abs(sme2.latitude[None, :] - grid.latitude[:, None]).argmin(axis=1)
    cols = np.abs(sme2.longitude[None, :] - grid.longitude[:, None]).argmin(axis=1)
    return sme2.layers[layer][np.ix_(rows, cols)]
