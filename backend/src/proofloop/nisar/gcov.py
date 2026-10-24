"""Read NISAR L2 GCOV (geocoded backscatter) granules.

GCOV grids are UTM (the EPSG code is in the `projection` dataset) at 10 to
20 m (frame 16 is 10 m), with 1D x/y axes of pixel centers. Backscatter terms are terrain-corrected
gamma0 power, NaN where missing. The `mask` layer holds the subswath number of
valid samples, 0 where any averaged radar sample was invalid, and 255 outside
the acquisition.
"""

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
from pyproj import Transformer

from proofloop.nisar.sme2 import BBox

_GRIDS = "science/LSAR/GCOV/grids/frequencyA/"

LAYERS = {"hh": "HHHH", "hv": "HVHV"}
_MASK_INVALID = 0
_MASK_OUTSIDE = 255


@dataclass(frozen=True)
class GcovGrid:
    epsg: int
    x: np.ndarray  # (cols,) pixel-center eastings in meters, west to east
    y: np.ndarray  # (rows,) pixel-center northings in meters, north to south
    layers: dict[str, np.ndarray]  # each (rows, cols), float32 linear power, NaN where invalid

    @property
    def spacing(self) -> float:
        return float(abs(self.x[1] - self.x[0])) if self.x.size > 1 else 0.0


def read_gcov(
    path: Path, bbox: BBox, pad_m: float = 0.0, layers: tuple[str, ...] = tuple(LAYERS)
) -> GcovGrid:
    """Read the pixels covering `bbox`, plus `pad_m` meters on every side.

    A frame-wide crop at 10 m is tens of millions of pixels, so read only the layers you need.
    """
    with h5py.File(path, "r") as f:
        epsg = _epsg(f)
        x = _dataset(f, "xCoordinates")[()].astype(np.float64)
        y = _dataset(f, "yCoordinates")[()].astype(np.float64)
        west, south, east, north = _projected_extent(bbox, epsg)
        cols = _span(x, west - pad_m, east + pad_m)
        rows = _span(y, south - pad_m, north + pad_m)

        mask = _dataset(f, "mask")[rows, cols]
        invalid = (mask == _MASK_INVALID) | (mask == _MASK_OUTSIDE)
        data = {}
        for name in layers:
            values = _dataset(f, LAYERS[name])[rows, cols].astype(np.float32)
            values[invalid | ~(values > 0)] = np.nan
            data[name] = values
    return GcovGrid(epsg=epsg, x=x[cols], y=y[rows], layers=data)


def _epsg(f: h5py.File) -> int:
    projection = _dataset(f, "projection")
    code = projection.attrs.get("epsg_code", projection[()])
    return int(np.asarray(code).item())


def _dataset(f: h5py.File, key: str) -> h5py.Dataset:
    node = f[_GRIDS + key]
    if not isinstance(node, h5py.Dataset):
        raise ValueError(f"{_GRIDS + key} is not a dataset")
    return node


def _projected_extent(bbox: BBox, epsg: int) -> tuple[float, float, float, float]:
    """West, south, east, north of the bbox in the granule's projection."""
    lon = np.linspace(bbox.west, bbox.east, 21)
    lat = np.linspace(bbox.south, bbox.north, 21)
    edge_lon = np.concatenate([lon, lon, np.full(21, bbox.west), np.full(21, bbox.east)])
    edge_lat = np.concatenate([np.full(21, bbox.south), np.full(21, bbox.north), lat, lat])
    x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(edge_lon, edge_lat)
    return float(np.min(x)), float(np.min(y)), float(np.max(x)), float(np.max(y))


def _span(axis: np.ndarray, low: float, high: float) -> slice:
    idx = np.flatnonzero((axis >= low) & (axis <= high))
    if idx.size == 0:
        raise ValueError(f"bbox [{low}, {high}] does not overlap axis [{axis.min()}, {axis.max()}]")
    return slice(int(idx[0]), int(idx[-1]) + 1)
