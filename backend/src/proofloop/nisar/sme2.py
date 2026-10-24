"""Read NISAR L3 SME2 (soil moisture) granules.

SME2 grids are EASE-Grid 2.0 global (EPSG:6933) at ~200 m, so every granule
on the same track and frame shares one grid and 1D latitude/longitude axes.
Besides soil moisture they carry gridded L-band backscatter (sigma0) and a
permanent water fraction, which makes them a cheap first hazard layer.
"""

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

_GRIDS = "science/LSAR/SME2/grids/"

LAYERS = {
    "soil_moisture": "soilMoisture",
    "sigma0_hh": "radarData/frequencyA/sigma0HH",
    "sigma0_hv": "radarData/frequencyA/sigma0HV",
    "water_fraction": "ancillaryData/waterbodyFraction",
}


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True)
class Sme2Grid:
    latitude: np.ndarray  # (rows,), north to south
    longitude: np.ndarray  # (cols,), west to east
    layers: dict[str, np.ndarray]  # each (rows, cols), float64, NaN where missing


def read_sme2(path: Path, bbox: BBox | None = None) -> Sme2Grid:
    with h5py.File(path, "r") as f:
        grids = f[_GRIDS]
        lat = grids["latitude"][()].astype(np.float64)
        lon = grids["longitude"][()].astype(np.float64)
        rows = slice(None) if bbox is None else _span(lat, bbox.south, bbox.north)
        cols = slice(None) if bbox is None else _span(lon, bbox.west, bbox.east)
        layers = {name: _read_layer(grids[key], rows, cols) for name, key in LAYERS.items()}
    return Sme2Grid(latitude=lat[rows], longitude=lon[cols], layers=layers)


def _span(axis: np.ndarray, low: float, high: float) -> slice:
    idx = np.flatnonzero((axis >= low) & (axis <= high))
    if idx.size == 0:
        raise ValueError(f"bbox [{low}, {high}] does not overlap axis [{axis.min()}, {axis.max()}]")
    return slice(int(idx[0]), int(idx[-1]) + 1)


def _read_layer(dataset: h5py.Dataset, rows: slice, cols: slice) -> np.ndarray:
    data = dataset[rows, cols].astype(np.float64)
    fill = dataset.attrs.get("_FillValue")
    if fill is not None:
        data[data == fill] = np.nan
    return data
