"""World builder seam: NISAR granules for a bounding box -> World (and its cache)."""

import numpy as np
from sme2_files import one_cell, write_sme2

from proofloop.nisar.sme2 import BBox
from proofloop.world.builder import build_world_from_sme2
from proofloop.world.store import load_world, save_world

EVERYWHERE = BBox(west=-84.0, south=29.0, east=-83.0, north=30.0)


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
    assert loaded.shelters == built.shelters
    assert loaded.reach_cells == built.reach_cells
