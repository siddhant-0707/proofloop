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
# Layers that cannot tell flood kinds apart use the hazard ramp.
LOW = np.array([253, 174, 97])
HIGH = np.array([215, 25, 28])
KIND_RAMPS = {
    FloodKind.OPEN_WATER: (np.array([116, 169, 207]), np.array([30, 58, 138])),
    FloodKind.UNDER_CANOPY: (np.array([186, 230, 253]), np.array([2, 132, 199])),
}
MIN_ALPHA, MAX_ALPHA = 110, 220
# Flood surface: evidence blurred over SURFACE_SIGMA cells (60 m each), drawn from
# SURFACE_THRESHOLD and at its strongest from SURFACE_FULL. Set from the Big Bend scene, where
# flagged cells are sparse: there the blurred evidence tops out near 0.26.
SURFACE_SIGMA = 4.0
SURFACE_THRESHOLD = 0.02
SURFACE_FULL = 0.12
SURFACE_MIN_ALPHA = 60
# (faintest, strongest, most opaque) per kind, for a light basemap: stronger evidence is
# deeper. Open water is the deepest and most opaque. Keep in sync with HazardMap.tsx.
OPEN_WATER_SURFACE = (np.array([96, 165, 250]), np.array([30, 58, 138]), 235)
CANOPY_SURFACE = (np.array([125, 211, 252]), np.array([3, 105, 161]), 175)
# Population density: transparent below 1 person/km^2, most opaque from 1,000.
POPULATION_RGB = np.array([51, 65, 85])
POPULATION_MIN_DENSITY = 1.0
POPULATION_DECADES = 3.0
# FEMA Special Flood Hazard Area: a light, even tint. Keep in sync with HazardMap.tsx.
FEMA_ZONE_RGB = np.array([20, 184, 166])
FEMA_ZONE_ALPHA = 70


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


def flood_surface_png(world: World) -> bytes:
    """Flood evidence smoothed into a water-like surface, for display only.

    Flagged cells' confidence is blurred over a few cells, separately for open water
    and for flooding under canopy, and drawn where the blurred evidence clears
    SURFACE_THRESHOLD: lone speckles fade out and clusters read as water. Open water
    is deep blue and nearly opaque; under canopy is a lighter sky blue and never as opaque,
    so it always reads fainter. A method that cannot tell kinds apart draws everything
    as open water. The Simulation still uses the binary flagged cells.
    """
    bounds = hazard_bounds(world)
    rows = _mercator_rows(world.grid.latitude, bounds.north, bounds.south)
    hazard = world.hazard
    evidence = np.where(hazard.flooded, hazard.confidence, 0.0)
    canopy = (
        hazard.kind == FloodKind.UNDER_CANOPY
        if hazard.kind is not None
        else np.zeros_like(hazard.flooded)
    )

    layers = []
    for in_kind, (low, high, max_alpha) in (
        (~canopy, OPEN_WATER_SURFACE),
        (canopy, CANOPY_SURFACE),
    ):
        density = _blur(np.where(in_kind, evidence, 0.0), SURFACE_SIGMA)[rows]
        t = np.clip((density - SURFACE_THRESHOLD) / (SURFACE_FULL - SURFACE_THRESHOLD), 0.0, 1.0)
        alpha = np.where(
            density >= SURFACE_THRESHOLD, SURFACE_MIN_ALPHA + (max_alpha - SURFACE_MIN_ALPHA) * t, 0
        )
        layers.append((low + (high - low) * t[..., None], alpha))

    (water_rgb, water_alpha), (canopy_rgb, canopy_alpha) = layers
    water_wins = water_alpha >= canopy_alpha
    rgb = np.where(water_wins[..., None], water_rgb, canopy_rgb).astype(np.uint8)
    alpha = np.maximum(water_alpha, canopy_alpha).astype(np.uint8)
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


def fema_zone_png(world: World) -> bytes:
    """Cells inside FEMA's Special Flood Hazard Area, one light tint; empty if not loaded."""
    bounds = hazard_bounds(world)
    rows = _mercator_rows(world.grid.latitude, bounds.north, bounds.south)
    zone = (
        world.in_fema_zone[rows]
        if world.in_fema_zone is not None
        else np.zeros((rows.size, world.grid.shape[1]), dtype=bool)
    )
    rgb = np.broadcast_to(FEMA_ZONE_RGB, (*zone.shape, 3)).astype(np.uint8)
    alpha = np.where(zone, FEMA_ZONE_ALPHA, 0).astype(np.uint8)
    return _png(rgb, alpha)


def _blur(values: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur, separable, with zeros beyond the edges."""
    radius = int(np.ceil(3 * sigma))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-(x**2) / (2 * sigma**2))
    kernel /= kernel.sum()
    rows = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="same"), 1, values)
    return np.apply_along_axis(lambda c: np.convolve(c, kernel, mode="same"), 0, rows)


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
