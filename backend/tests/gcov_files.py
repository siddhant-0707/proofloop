"""Write small synthetic NISAR GCOV granules for tests.

The scene is a 48 x 48 grid of 20 m pixels in UTM zone 17N centered on
Steinhatchee, inside the SME2 test grid's central cell.
"""

from pathlib import Path

import h5py
import numpy as np
from pyproj import Transformer

from proofloop.nisar.gcov import LAYERS
from proofloop.nisar.sme2 import BBox

EPSG = 32617
SPACING = 20.0
SIZE = 48
CENTER_LON, CENTER_LAT = -83.4, 29.8
_TO_UTM = Transformer.from_crs(4326, EPSG, always_xy=True)
_cx, _cy = _TO_UTM.transform(CENTER_LON, CENTER_LAT)
X = round(_cx / SPACING) * SPACING + (np.arange(SIZE) - SIZE / 2 + 0.5) * SPACING
Y = round(_cy / SPACING) * SPACING - (np.arange(SIZE) - SIZE / 2 + 0.5) * SPACING
# Well inside the scene, leaving room for the builder's padding.
SCENE_BBOX = BBox(west=-83.403, south=29.797, east=-83.397, north=29.803)


def write_gcov(
    path: Path, hh: np.ndarray | float = 0.05, mask: np.ndarray | int = 1, **layers: float
) -> Path:
    """Backscatter defaults to unchanging land at about -13 dB HH; mask 1 is valid."""
    values = {"hh": hh, "hv": layers.get("hv", 0.01)}
    with h5py.File(path, "w") as f:
        grids = f.create_group("science/LSAR/GCOV/grids/frequencyA")
        grids["xCoordinates"] = X
        grids["yCoordinates"] = Y
        grids.create_dataset("projection", data=np.uint32(EPSG)).attrs["epsg_code"] = EPSG
        for name, key in LAYERS.items():
            grids[key] = np.broadcast_to(np.asarray(values[name], np.float32), (SIZE, SIZE))
        grids["mask"] = np.broadcast_to(np.asarray(mask, np.uint8), (SIZE, SIZE))
    return path


def center_patch(value: float, base: float, half_px: int = 9) -> np.ndarray:
    """`base` everywhere except a square of 2 * half_px pixels around the scene center."""
    grid = np.full((SIZE, SIZE), base, dtype=np.float32)
    lo, hi = SIZE // 2 - half_px, SIZE // 2 + half_px
    grid[lo:hi, lo:hi] = value
    return grid
