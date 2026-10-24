import h5py
import numpy as np
import pytest

from proofloop.nisar.sme2 import LAYERS, BBox, read_sme2

FILL = -9999.0


@pytest.fixture
def granule(tmp_path):
    path = tmp_path / "sme2.h5"
    lat = np.array([30.0, 29.8, 29.6, 29.4], dtype=np.float32)
    lon = np.array([-84.0, -83.8, -83.6], dtype=np.float32)
    with h5py.File(path, "w") as f:
        grids = f.create_group("science/LSAR/SME2/grids")
        grids["latitude"] = lat
        grids["longitude"] = lon
        for i, key in enumerate(LAYERS.values()):
            data = np.full((4, 3), float(i), dtype=np.float32)
            data[0, 0] = FILL
            grids.create_dataset(key, data=data).attrs["_FillValue"] = np.float32(FILL)
    return path


def test_reads_all_layers_and_masks_fill(granule):
    grid = read_sme2(granule)

    assert grid.latitude.shape == (4,)
    assert grid.longitude.shape == (3,)
    assert set(grid.layers) == set(LAYERS)
    assert np.isnan(grid.layers["soil_moisture"][0, 0])
    assert grid.layers["sigma0_hh"][1, 1] == 1.0


def test_crops_to_bbox(granule):
    grid = read_sme2(granule, BBox(west=-83.9, south=29.5, east=-83.5, north=29.9))

    np.testing.assert_allclose(grid.latitude, [29.8, 29.6], rtol=1e-6)
    np.testing.assert_allclose(grid.longitude, [-83.8, -83.6], rtol=1e-6)
    assert grid.layers["water_fraction"].shape == (2, 2)


def test_rejects_bbox_outside_granule(granule):
    with pytest.raises(ValueError, match="does not overlap"):
        read_sme2(granule, BBox(west=-80.0, south=25.0, east=-79.0, north=26.0))
