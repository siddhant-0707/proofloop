"""The flood surface: NISAR flood evidence smoothed into a water-like image for the map."""

import io

import numpy as np
from PIL import Image

from proofloop.api.hazard_image import flood_surface_png, hazard_png
from proofloop.world import FloodKind, Grid, HazardLayer, World

SIZE = 60


def world_with(*patches: tuple[FloodKind, slice, slice], confidence: float = 0.9) -> World:
    """A SIZE x SIZE World, flooded only in the given (kind, rows, cols) patches."""
    kind = np.zeros((SIZE, SIZE), dtype=np.uint8)
    for flood_kind, rows, cols in patches:
        kind[rows, cols] = flood_kind
    flooded = kind != FloodKind.NONE
    return World(
        grid=Grid(
            latitude=np.linspace(29.70, 29.70 - 0.00054 * (SIZE - 1), SIZE),
            longitude=np.linspace(-83.40, -83.40 + 0.00062 * (SIZE - 1), SIZE),
        ),
        hazard=HazardLayer(
            flooded=flooded,
            confidence=np.where(flooded, confidence, 0.0),
            method="gcov",
            kind=kind,
        ),
        population=np.zeros((SIZE, SIZE)),
    )


def rgba(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA")).astype(int)


def test_open_water_is_opaque_blue_and_dry_land_is_clear():
    world = world_with((FloodKind.OPEN_WATER, slice(20, 40), slice(20, 40)))

    image = rgba(flood_surface_png(world))

    r, g, b, a = image[30, 30]
    assert a >= 180 and b > r and b > g
    assert image[2, 2, 3] == 0


def test_flooding_under_canopy_is_fainter_than_open_water():
    world = world_with(
        (FloodKind.OPEN_WATER, slice(10, 30), slice(5, 25)),
        (FloodKind.UNDER_CANOPY, slice(10, 30), slice(35, 55)),
    )

    image = rgba(flood_surface_png(world))

    open_water, canopy = image[20, 15, 3], image[20, 45, 3]
    assert 0 < canopy < open_water


def test_a_lone_flagged_cell_is_too_weak_to_draw():
    world = world_with(
        (FloodKind.OPEN_WATER, slice(30, 31), slice(30, 31)),
        (FloodKind.UNDER_CANOPY, slice(10, 11), slice(10, 11)),
    )

    image = rgba(flood_surface_png(world))

    assert image[..., 3].max() == 0


def test_covers_the_same_area_as_the_hazard_image():
    world = world_with((FloodKind.OPEN_WATER, slice(20, 40), slice(20, 40)))

    surface = Image.open(io.BytesIO(flood_surface_png(world)))
    hazard = Image.open(io.BytesIO(hazard_png(world)))

    assert surface.size == hazard.size == (SIZE, SIZE)
