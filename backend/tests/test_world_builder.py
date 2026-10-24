"""World builder seam: NISAR granules for a bounding box -> World (and its cache)."""

from pathlib import Path

import numpy as np
import pytest
from gcov_files import CENTER_LAT, CENTER_LON, SCENE_BBOX, center_patch, write_gcov
from sme2_files import one_cell, write_sme2

from proofloop.exposure.census import Block
from proofloop.exposure.shelters import ShelterSite
from proofloop.nisar.sme2 import BBox
from proofloop.world import FloodKind, Grid, HazardLayer, World
from proofloop.world.builder import (
    GranulePair,
    build_world,
    build_world_from_gcov,
    build_world_from_sme2,
    with_exposure,
)
from proofloop.world.store import load_world, save_world

EVERYWHERE = BBox(west=-84.0, south=29.0, east=-83.0, north=30.0)
FOREST = 0.1  # -10 dB HH, bright enough for double bounce


def _gcov_world(
    tmp_path: Path,
    before_hh: np.ndarray | float,
    after_hh: np.ndarray | float,
    after_mask: np.ndarray | int = 1,
    water_fraction: float = 0.0,
) -> World:
    return build_world_from_gcov(
        write_gcov(tmp_path / "before.h5", hh=before_hh),
        write_gcov(tmp_path / "after.h5", hh=after_hh, mask=after_mask),
        SCENE_BBOX,
        permanent_water=write_sme2(tmp_path / "sme2.h5", water_fraction=water_fraction),
    )


def _center(world: World) -> tuple[int, int]:
    row = int(np.abs(world.grid.latitude - CENTER_LAT).argmin())
    col = int(np.abs(world.grid.longitude - CENTER_LON).argmin())
    return row, col


def test_gcov_darkening_is_flagged_as_open_water_flooding(tmp_path):
    world = _gcov_world(tmp_path, 0.05, center_patch(0.0125, base=0.05))  # -6 dB

    center = _center(world)
    assert world.hazard.method == "gcov"
    assert world.hazard.flooded[center]
    assert world.hazard.kind is not None
    assert world.hazard.kind[center] == FloodKind.OPEN_WATER
    assert world.hazard.confidence[center] == 1.0
    assert not world.hazard.flooded[0, 0] and not world.hazard.flooded[-1, -1]
    assert world.hazard.kind[0, 0] == FloodKind.NONE


def test_gcov_brightening_of_vegetation_is_flagged_as_flooding_under_canopy(tmp_path):
    world = _gcov_world(tmp_path, FOREST, center_patch(0.4, base=FOREST))  # +6 dB

    center = _center(world)
    assert world.hazard.flooded[center]
    assert world.hazard.kind is not None
    assert world.hazard.kind[center] == FloodKind.UNDER_CANOPY
    assert not world.hazard.flooded[0, 0]


def test_gcov_brightening_of_bare_fields_is_not_flooding_under_canopy(tmp_path):
    world = _gcov_world(tmp_path, 0.025, center_patch(0.1, base=0.025))  # -16 dB, +6 dB

    assert not world.hazard.flooded.any()


def test_gcov_darkening_that_is_still_too_bright_for_water_is_not_flagged(tmp_path):
    world = _gcov_world(tmp_path, 1.0, center_patch(0.25, base=1.0))  # 0 dB -> -6 dB

    assert not world.hazard.flooded.any()


def test_gcov_scene_wide_wet_soil_brightening_is_not_flooding(tmp_path):
    world = _gcov_world(tmp_path, FOREST, 0.25)  # +4 dB everywhere

    assert not world.hazard.flooded.any()


def test_gcov_canopy_flooding_is_measured_beyond_the_scene_wide_brightening(tmp_path):
    # Wet soil brightens the scene by 2 dB; the patch brightens by 6 dB, 4 dB beyond that.
    world = _gcov_world(tmp_path, FOREST, center_patch(0.4, base=0.158))

    center = _center(world)
    assert world.hazard.flooded[center]
    assert np.isclose(world.hazard.confidence[center], 4 / 6, atol=0.01)
    assert not world.hazard.flooded[0, 0]


def test_gcov_mild_changes_are_not_flagged(tmp_path):
    world = _gcov_world(tmp_path, FOREST, 0.15)  # +1.8 dB everywhere

    assert not world.hazard.flooded.any()


def test_gcov_permanent_water_is_never_flagged(tmp_path):
    world = _gcov_world(tmp_path, FOREST, center_patch(0.4, base=FOREST), water_fraction=1.0)

    assert not world.hazard.flooded.any()
    assert world.hazard.confidence[_center(world)] == 0.0


def test_gcov_cells_already_dark_before_the_storm_are_permanent_water(tmp_path):
    # A river at -23 dB that a windy after pass brightens by 6 dB is not new flooding.
    world = _gcov_world(tmp_path, center_patch(0.005, base=FOREST), center_patch(0.02, base=FOREST))

    assert not world.hazard.flooded.any()


def test_gcov_invalid_or_missing_samples_carry_no_hazard(tmp_path):
    after = center_patch(0.4, base=FOREST)
    invalid = center_patch(0, base=1).astype(np.uint8)

    world = _gcov_world(tmp_path, FOREST, after, after_mask=invalid)

    assert not world.hazard.flooded.any()
    assert world.hazard.confidence[_center(world)] == 0.0


def test_gcov_world_tiles_the_bounding_box_in_60_m_cells(tmp_path):
    world = _gcov_world(tmp_path, 0.05, 0.05)

    lat, lon = world.grid.latitude, world.grid.longitude
    assert SCENE_BBOX.south < lat.min() < lat.max() < SCENE_BBOX.north
    assert SCENE_BBOX.west < lon.min() < lon.max() < SCENE_BBOX.east
    assert np.isclose(abs(lat[1] - lat[0]) * 111_320, 60, rtol=0.1)
    assert world.hazard.flooded.shape == world.population.shape == world.grid.shape
    assert world.reach_cells == 1000  # 60 km of travel


def _dry_world() -> World:
    """4 x 3 cells of 0.1 degrees; outer edges 30.0 N to 29.6 N and 84.0 W to 83.7 W."""
    grid = Grid(
        latitude=np.array([29.95, 29.85, 29.75, 29.65]),
        longitude=np.array([-83.95, -83.85, -83.75]),
    )
    no_flood = np.zeros(grid.shape)
    return World(
        grid=grid,
        hazard=HazardLayer(flooded=no_flood > 0, confidence=no_flood, method="hand-built"),
        population=no_flood,
    )


CELL_M2 = 0.1 * 0.1 * 111_320**2 * np.cos(np.radians(29.8))


def _block(
    population: float, west: float, south: float, east: float, north: float, area_cells=None
) -> Block:
    width, height = round((east - west) / 0.1), round((north - south) / 0.1)
    return Block(
        geoid=f"{west}{south}",
        population=population,
        area_m2=(area_cells if area_cells is not None else width * height) * CELL_M2,
        point=((west + east) / 2, (south + north) / 2),
        rings=(((west, north), (east, north), (east, south), (west, south), (west, north)),),
    )


def test_block_population_is_spread_evenly_over_the_cells_it_covers():
    block = _block(40, west=-84.0, south=29.8, east=-83.8, north=30.0)

    world = with_exposure(_dry_world(), [block], [])

    np.testing.assert_allclose(
        world.population,
        [[10, 10, 0], [10, 10, 0], [0, 0, 0], [0, 0, 0]],
    )


def test_a_block_inside_another_keeps_its_own_people():
    county = _block(110, west=-84.0, south=29.6, east=-83.7, north=30.0)
    town = _block(7, west=-83.8, south=29.6, east=-83.7, north=29.7)

    world = with_exposure(_dry_world(), [town, county], [])

    assert world.population[3, 2] == 7
    np.testing.assert_allclose(world.population[:3], 10)
    assert world.population.sum() == pytest.approx(117)


def test_a_block_smaller_than_a_cell_puts_everyone_at_its_interior_point():
    tiny = _block(5, west=-83.86, south=29.74, east=-83.84, north=29.76, area_cells=0.04)

    world = with_exposure(_dry_world(), [tiny], [])

    assert world.population[2, 1] == 5
    assert world.population.sum() == 5


def test_a_block_cut_by_the_grid_edge_keeps_only_its_share_inside():
    straddling = _block(40, west=-84.2, south=29.9, east=-83.8, north=30.0)  # half off the west
    outside = _block(99, west=-85.0, south=29.0, east=-84.5, north=29.5)

    world = with_exposure(_dry_world(), [straddling, outside], [])

    np.testing.assert_allclose(world.population[0], [10, 10, 0])
    assert world.population.sum() == pytest.approx(20)


def test_shelters_are_placed_in_the_cell_that_contains_them():
    site = ShelterSite("s1", "School", "1 Main St", latitude=29.72, longitude=-83.78, capacity=300)

    world = with_exposure(_dry_world(), [], [site])

    (shelter,) = world.shelters
    assert (shelter.id, shelter.row, shelter.col) == ("s1", 2, 2)
    assert shelter.capacity == 300
    assert shelter.cost == site.cost


def test_a_shelter_off_the_grid_is_rejected():
    site = ShelterSite("far", "Far School", "Perry", latitude=30.5, longitude=-83.8, capacity=100)

    with pytest.raises(ValueError, match="off the grid"):
        with_exposure(_dry_world(), [], [site])


def test_world_falls_back_to_sme2_when_gcov_is_missing(tmp_path):
    sme2 = GranulePair(
        write_sme2(tmp_path / "sme2-before.h5"), write_sme2(tmp_path / "sme2-after.h5")
    )
    missing = GranulePair(tmp_path / "gcov-before.h5", tmp_path / "gcov-after.h5")

    world = build_world(EVERYWHERE, sme2, missing)

    assert world.hazard.method == "sme2"
    assert world.hazard.kind is None


def test_world_uses_gcov_when_both_granules_are_present(tmp_path):
    sme2 = GranulePair(
        write_sme2(tmp_path / "sme2-before.h5"), write_sme2(tmp_path / "sme2-after.h5")
    )
    gcov = GranulePair(
        write_gcov(tmp_path / "gcov-before.h5"), write_gcov(tmp_path / "gcov-after.h5")
    )

    world = build_world(SCENE_BBOX, sme2, gcov)

    assert world.hazard.method == "gcov"


def test_a_cached_gcov_world_keeps_its_flood_kinds(tmp_path):
    built = _gcov_world(tmp_path, FOREST, center_patch(0.4, base=FOREST))
    cache = tmp_path / "world.npz"

    save_world(built, cache)
    loaded = load_world(cache)

    assert built.hazard.kind is not None and loaded.hazard.kind is not None
    assert (built.hazard.kind == FloodKind.UNDER_CANOPY).any()
    np.testing.assert_array_equal(loaded.hazard.kind, built.hazard.kind)
    assert loaded.hazard.method == "gcov"
    assert loaded.reach_cells == built.reach_cells


def test_strong_backscatter_brightening_is_flagged_as_hazard(tmp_path):
    before = write_sme2(tmp_path / "before.h5", sigma0_hh=0.01)
    after = write_sme2(tmp_path / "after.h5", sigma0_hh=one_cell(0.04, base=0.01))  # +6 dB

    world = build_world_from_sme2(before, after, EVERYWHERE)

    assert world.hazard.flooded.tolist() == [
        [False, False, False],
        [False, True, False],
        [False, False, False],
    ]
    assert world.hazard.confidence[1, 1] == 1.0
    assert world.hazard.method == "sme2"


def test_strong_backscatter_darkening_from_open_water_is_flagged(tmp_path):
    before = write_sme2(tmp_path / "before.h5", sigma0_hh=0.04)
    after = write_sme2(tmp_path / "after.h5", sigma0_hh=one_cell(0.01, base=0.04))  # -6 dB

    world = build_world_from_sme2(before, after, EVERYWHERE)

    assert world.hazard.flooded[1, 1]
    assert world.hazard.flooded.sum() == 1


def test_soil_wetting_is_flagged_even_without_backscatter_change(tmp_path):
    before = write_sme2(tmp_path / "before.h5", soil_moisture=0.20)
    after = write_sme2(tmp_path / "after.h5", soil_moisture=one_cell(0.32, base=0.20))

    world = build_world_from_sme2(before, after, EVERYWHERE)

    assert world.hazard.flooded.sum() == 1
    assert np.isclose(world.hazard.confidence[1, 1], 0.6)


def test_mild_changes_are_not_flagged(tmp_path):
    before = write_sme2(tmp_path / "before.h5", sigma0_hh=0.010, soil_moisture=0.20)
    after = write_sme2(tmp_path / "after.h5", sigma0_hh=0.015, soil_moisture=0.25)  # +1.8 dB

    world = build_world_from_sme2(before, after, EVERYWHERE)

    assert not world.hazard.flooded.any()


def test_permanent_water_is_never_flagged(tmp_path):
    gulf = one_cell(1.0, base=0.0)
    before = write_sme2(tmp_path / "before.h5", sigma0_hh=0.01, water_fraction=gulf)
    after = write_sme2(tmp_path / "after.h5", sigma0_hh=0.04, water_fraction=gulf)  # +6 dB

    world = build_world_from_sme2(before, after, EVERYWHERE)

    assert world.hazard.flooded.sum() == 8
    assert not world.hazard.flooded[1, 1]
    assert world.hazard.confidence[1, 1] == 0.0


def test_cells_missing_radar_data_carry_no_hazard(tmp_path):
    before = write_sme2(tmp_path / "before.h5", sigma0_hh=one_cell(np.nan, base=0.01))
    after = write_sme2(tmp_path / "after.h5", sigma0_hh=0.04, soil_moisture=np.nan)

    world = build_world_from_sme2(before, after, EVERYWHERE)

    assert not world.hazard.flooded[1, 1]
    assert world.hazard.confidence[1, 1] == 0.0
    assert world.hazard.flooded.sum() == 8


def test_world_is_cropped_to_the_bounding_box(tmp_path):
    before = write_sme2(tmp_path / "before.h5")
    after = write_sme2(tmp_path / "after.h5")

    world = build_world_from_sme2(
        before, after, BBox(west=-83.45, south=29.65, east=-83.25, north=29.85)
    )

    np.testing.assert_allclose(world.grid.latitude, [29.8, 29.7], rtol=1e-6)
    np.testing.assert_allclose(world.grid.longitude, [-83.4, -83.3], rtol=1e-6)
    assert world.hazard.flooded.shape == world.population.shape == (2, 2)


def test_a_cached_world_loads_without_the_source_granules(tmp_path):
    before = write_sme2(tmp_path / "before.h5", sigma0_hh=0.01)
    after = write_sme2(tmp_path / "after.h5", sigma0_hh=one_cell(0.04, base=0.01))
    built = build_world_from_sme2(before, after, EVERYWHERE)
    cache = tmp_path / "world.npz"

    save_world(built, cache)
    before.unlink()
    after.unlink()
    loaded = load_world(cache)

    np.testing.assert_array_equal(loaded.grid.latitude, built.grid.latitude)
    np.testing.assert_array_equal(loaded.grid.longitude, built.grid.longitude)
    np.testing.assert_array_equal(loaded.hazard.flooded, built.hazard.flooded)
    np.testing.assert_array_equal(loaded.hazard.confidence, built.hazard.confidence)
    np.testing.assert_array_equal(loaded.population, built.population)
    assert loaded.hazard.method == "sme2"
    assert loaded.hazard.kind is None
    assert loaded.shelters == built.shelters
    assert loaded.reach_cells == built.reach_cells
