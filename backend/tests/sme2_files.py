"""Write small synthetic NISAR SME2 granules for tests."""

from pathlib import Path

import h5py
import numpy as np

from proofloop.nisar.sme2 import LAYERS

FILL = -9999.0
LATITUDE = np.array([29.9, 29.8, 29.7], dtype=np.float32)
LONGITUDE = np.array([-83.5, -83.4, -83.3], dtype=np.float32)


def write_sme2(path: Path, **layers: np.ndarray | float) -> Path:
    """Layers default to dry, unchanging land; NaN values are written as fill."""
    defaults = {"soil_moisture": 0.2, "sigma0_hh": 0.01, "sigma0_hv": 0.002, "water_fraction": 0.0}
    with h5py.File(path, "w") as f:
        grids = f.create_group("science/LSAR/SME2/grids")
        grids["latitude"] = LATITUDE
        grids["longitude"] = LONGITUDE
        for name, key in LAYERS.items():
            value = layers.get(name, defaults[name])
            data = np.broadcast_to(np.asarray(value, dtype=np.float32), (3, 3)).copy()
            data[np.isnan(data)] = FILL
            grids.create_dataset(key, data=data).attrs["_FillValue"] = np.float32(FILL)
    return path


def one_cell(value: float, base: float, row: int = 1, col: int = 1) -> np.ndarray:
    grid = np.full((3, 3), base, dtype=np.float32)
    grid[row, col] = value
    return grid
