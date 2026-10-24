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

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from pyproj import Transformer

from proofloop.exposure.census import Block
from proofloop.exposure.shelters import ShelterSite
from proofloop.nisar.gcov import GcovGrid, read_gcov
from proofloop.nisar.sme2 import BBox, Sme2Grid, read_sme2
from proofloop.world import FloodKind, Grid, HazardLayer, Shelter, World

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
SME2_CELL_M = 200.0
# How far people can travel to a shelter along the grid, used to size World.reach_cells.
# Coastal towns are 30 to 55 km from the shelters in Cross City and Perry.
TRAVEL_REACH_M = 60_000.0
_METERS_PER_DEGREE = 111_320.0


@dataclass(frozen=True)
class GranulePair:
    before: Path
    after: Path

    def exist(self) -> bool:
        return self.before.exists() and self.after.exists()


def build_world(bbox: BBox, sme2: Sequence[GranulePair], gcov: Sequence[GranulePair] = ()) -> World:
    """Each argument holds one before/after pair per frame. Use GCOV when every granule is
    present, otherwise fall back to the first frame's SME2."""
    if gcov and all(pair.exist() for pair in gcov):
        return build_world_from_gcov(gcov, bbox, permanent_water=[p.before for p in sme2])
    return build_world_from_sme2(sme2[0].before, sme2[0].after, bbox)


def build_world_from_gcov(
    frames: Sequence[GranulePair],
    bbox: BBox,
    permanent_water: Sequence[Path],
    cell_m: float = GCOV_CELL_M,
) -> World:
    """`frames` are GCOV before/after pairs. Where frames overlap, each cell takes both passes
    from the first frame that measured it on both. `permanent_water` are SME2 granules whose
    water fraction masks the Gulf and rivers; cells none of them cover are never flagged."""
    grid = _latlon_grid(bbox, cell_m)
    pre_hh, post_hh = np.full(grid.shape, np.nan), np.full(grid.shape, np.nan)
    for frame in frames:
        pre = _resample(read_gcov(frame.before, bbox, cell_m, layers=("hh",)), "hh", grid, cell_m)
        post = _resample(read_gcov(frame.after, bbox, cell_m, layers=("hh",)), "hh", grid, cell_m)
        fill = ~(np.isfinite(pre_hh) & np.isfinite(post_hh)) & np.isfinite(pre) & np.isfinite(post)
        pre_hh[fill], post_hh[fill] = pre[fill], post[fill]
    water_fraction = np.full(grid.shape, np.nan)
    for path in permanent_water:
        sampled = _sample_sme2(read_sme2(path), "water_fraction", grid)
        water_fraction = np.where(np.isnan(water_fraction), sampled, water_fraction)

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
        reach_cells=round(TRAVEL_REACH_M / SME2_CELL_M),
    )


def with_exposure(world: World, blocks: Sequence[Block], sites: Sequence[ShelterSite]) -> World:
    """Add Census block population and shelters to a World built from radar."""
    return replace(
        world,
        population=rasterize_population(world.grid, blocks),
        shelters=tuple(_place_shelter(world.grid, site) for site in sites),
    )


def rasterize_population(grid: Grid, blocks: Sequence[Block]) -> np.ndarray:
    """People per cell, each block's population spread evenly over the cells it covers.

    Blocks partition the county, and a block's rings may enclose smaller blocks, so
    blocks are drawn largest first and nested blocks overwrite their surroundings.
    A block too small to cover any cell center puts everyone in its interior point's
    cell. A block cut by the grid edge keeps only the share of its area inside.
    """
    west, north, dlon, dlat = _edges(grid)
    label = np.full(grid.shape, -1, dtype=np.int64)
    for i in sorted(range(len(blocks)), key=lambda i: blocks[i].area_m2, reverse=True):
        rings = [np.array(ring, dtype=np.float64) for ring in blocks[i].rings if len(ring) >= 3]
        if rings:
            # Cell units: cell (row, col) is centered at (x, y) = (col, row).
            cells = [
                np.column_stack([(r[:, 0] - west) / dlon, (north - r[:, 1]) / dlat]) - 0.5
                for r in rings
            ]
            _fill_rings(label, cells, i)
    covered = label >= 0
    counts = np.bincount(label[covered], minlength=len(blocks))

    cell_m2 = dlat * dlon * _METERS_PER_DEGREE**2 * np.cos(np.radians(grid.latitude.mean()))
    per_cell = np.zeros(len(blocks))
    population = np.zeros(grid.shape)
    for i, block in enumerate(blocks):
        if counts[i] == 0:
            cell = _cell_of(grid, *block.point)
            if cell is not None:
                population[cell] += block.population
        elif _inside(grid, block):
            per_cell[i] = block.population / counts[i]
        else:
            share = min(1.0, counts[i] * cell_m2 / block.area_m2) if block.area_m2 else 1.0
            per_cell[i] = block.population * share / counts[i]
    population[covered] += per_cell[label[covered]]
    return population


def _fill_rings(label: np.ndarray, rings: list[np.ndarray], value: int) -> None:
    """Set cells whose centers lie inside the rings (even-odd rule, so holes stay out)."""
    closed = [r if np.array_equal(r[0], r[-1]) else np.vstack([r, r[:1]]) for r in rings]
    start = np.concatenate([r[:-1] for r in closed])
    end = np.concatenate([r[1:] for r in closed])
    rows, cols = label.shape
    first = max(0, int(np.ceil(start[:, 1].min())))
    last = min(rows - 1, int(np.floor(start[:, 1].max())))
    if first > last:
        return
    y = np.arange(first, last + 1, dtype=np.float64)[:, None]
    (x0, y0), (x1, y1) = start.T, end.T
    crosses = (y0 <= y) != (y1 <= y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x = np.where(crosses, x0 + (y - y0) * (x1 - x0) / (y1 - y0), np.inf)
    x.sort(axis=1)
    for i, count in enumerate(crosses.sum(axis=1)):
        for left, right in zip(x[i, 0:count:2], x[i, 1:count:2], strict=True):
            c0, c1 = max(0, int(np.ceil(left))), min(cols, int(np.ceil(right)))
            if c0 < c1:
                label[first + i, c0:c1] = value


def _place_shelter(grid: Grid, site: ShelterSite) -> Shelter:
    cell = _cell_of(grid, site.longitude, site.latitude)
    if cell is None:
        raise ValueError(
            f"shelter {site.id} at ({site.latitude}, {site.longitude}) is off the grid"
        )
    return Shelter(
        id=site.id,
        name=site.name,
        row=cell[0],
        col=cell[1],
        capacity=site.capacity,
        cost=site.cost,
    )


def _edges(grid: Grid) -> tuple[float, float, float, float]:
    """West and north outer edges and the cell size, in degrees."""
    dlat = abs(float(grid.latitude[1] - grid.latitude[0])) if grid.latitude.size > 1 else 1.0
    dlon = abs(float(grid.longitude[1] - grid.longitude[0])) if grid.longitude.size > 1 else 1.0
    return grid.longitude[0] - dlon / 2, grid.latitude[0] + dlat / 2, dlon, dlat


def _cell_of(grid: Grid, lon: float, lat: float) -> tuple[int, int] | None:
    west, north, dlon, dlat = _edges(grid)
    row, col = int(np.floor((north - lat) / dlat)), int(np.floor((lon - west) / dlon))
    rows, cols = grid.shape
    return (row, col) if 0 <= row < rows and 0 <= col < cols else None


def _inside(grid: Grid, block: Block) -> bool:
    """Whether every vertex of the block lies on the grid or its outer edge."""
    west, north, dlon, dlat = _edges(grid)
    rows, cols = grid.shape
    lon, lat = np.array([p for ring in block.rings for p in ring]).T
    east, south = west + cols * dlon, north - rows * dlat
    eps = 1e-9
    inside = (lon >= west - eps) & (lon <= east + eps) & (lat >= south - eps) & (lat <= north + eps)
    return bool(inside.all())


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
    """The nearest SME2 cell's value at each grid cell, NaN beyond the granule's edge."""
    rows = np.abs(sme2.latitude[None, :] - grid.latitude[:, None]).argmin(axis=1)
    cols = np.abs(sme2.longitude[None, :] - grid.longitude[:, None]).argmin(axis=1)
    values = sme2.layers[layer][np.ix_(rows, cols)]
    values[_beyond(sme2.latitude, rows, grid.latitude), :] = np.nan
    values[:, _beyond(sme2.longitude, cols, grid.longitude)] = np.nan
    return values


def _beyond(axis: np.ndarray, nearest: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Whether each target lies more than half a cell from its nearest point on `axis`."""
    half = abs(float(axis[1] - axis[0])) / 2 if axis.size > 1 else np.inf
    return np.abs(axis[nearest] - targets) > half + 1e-9
