"""Render a World's hazard and population layers as georeferenced PNGs for MapLibre.

MapLibre stretches an image linearly between its four corners in Web Mercator,
so rows are resampled from the World's latitude axis onto rows evenly spaced
in Mercator y. Columns are already evenly spaced in longitude.
"""

import io

import numpy as np
from PIL import Image

from proofloop.nisar.sme2 import BBox
from proofloop.world import FloodKind, World

# Colour ramps from low to high confidence (RGB), alpha rises with confidence.
# Layers that cannot tell flood kinds apart use the hazard ramp. Keep in sync with HazardMap.tsx.
LOW = np.array([253, 174, 97])
HIGH = np.array([215, 25, 28])
KIND_RAMPS = {
    FloodKind.OPEN_WATER: (np.array([116, 169, 207]), np.array([30, 58, 138])),
    FloodKind.UNDER_CANOPY: (np.array([186, 230, 253]), np.array([2, 132, 199])),
}
MIN_ALPHA, MAX_ALPHA = 110, 220
# Population density: transparent below 1 person/km^2, most opaque from 1,000.
POPULATION_RGB = np.array([51, 65, 85])
POPULATION_MIN_DENSITY = 1.0
POPULATION_DECADES = 3.0


def hazard_bounds(world: World) -> BBox:
    """Outer cell edges in degrees."""
    lat, lon = world.grid.latitude, world.grid.longitude
    half_lat = abs(lat[1] - lat[0]) / 2 if lat.size > 1 else 0.0
    half_lon = abs(lon[1] - lon[0]) / 2 if lon.size > 1 else 0.0
    return BBox(
        west=float(lon.min() - half_lon),
        south=float(lat.min() - half_lat),
        east=float(lon.max() + half_lon),
        north=float(lat.max() + half_lat),
    )


def hazard_png(world: World) -> bytes:
    bounds = hazard_bounds(world)
    rows = _mercator_rows(world.grid.latitude, bounds.north, bounds.south)
    flooded = world.hazard.flooded[rows]
    confidence = world.hazard.confidence[rows]

    t = np.clip((confidence - 0.5) / 0.5, 0.0, 1.0)[..., None]
    rgb = (LOW + (HIGH - LOW) * t).astype(np.uint8)
    if world.hazard.kind is not None:
        kind = world.hazard.kind[rows]
        for k, (low, high) in KIND_RAMPS.items():
            rgb[kind == k] = (low + (high - low) * t).astype(np.uint8)[kind == k]
    alpha = np.where(flooded, MIN_ALPHA + (MAX_ALPHA - MIN_ALPHA) * t[..., 0], 0).astype(np.uint8)

    return _png(rgb, alpha)


def population_png(world: World) -> bytes:
    """People per km^2, one colour with opacity rising on a log scale."""
    bounds = hazard_bounds(world)
    rows = _mercator_rows(world.grid.latitude, bounds.north, bounds.south)
    lat, lon = world.grid.latitude, world.grid.longitude
    dlat = abs(lat[1] - lat[0]) if lat.size > 1 else 0.0
    dlon = abs(lon[1] - lon[0]) if lon.size > 1 else 0.0
    cell_km2 = (dlat * 111.32) * (dlon * 111.32 * np.cos(np.radians(lat)))
    density = (world.population / np.maximum(cell_km2, 1e-9)[:, None])[rows]

    with np.errstate(divide="ignore"):
        t = np.clip(np.log10(density / POPULATION_MIN_DENSITY) / POPULATION_DECADES, 0.0, 1.0)
    rgb = np.broadcast_to(POPULATION_RGB, (*density.shape, 3)).astype(np.uint8)
    alpha = np.where(density >= POPULATION_MIN_DENSITY, 40 + 160 * t, 0).astype(np.uint8)
    return _png(rgb, alpha)


def _png(rgb: np.ndarray, alpha: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(np.dstack([rgb, alpha]), mode="RGBA").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _mercator_rows(latitude: np.ndarray, north: float, south: float) -> np.ndarray:
    """For each output row, evenly spaced in Mercator y, the nearest World row."""
    y = np.linspace(_mercator_y(north), _mercator_y(south), latitude.size, endpoint=False)
    y += (y[1] - y[0]) / 2 if latitude.size > 1 else 0.0
    targets = np.degrees(np.arctan(np.sinh(y)))
    return np.abs(latitude[None, :] - targets[:, None]).argmin(axis=1)


def _mercator_y(lat: float) -> float:
    return float(np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)))
