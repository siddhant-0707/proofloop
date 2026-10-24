"""Render a World's hazard layer as a georeferenced PNG for a MapLibre image source.

MapLibre stretches an image linearly between its four corners in Web Mercator,
so rows are resampled from the World's latitude axis onto rows evenly spaced
in Mercator y. Columns are already evenly spaced in longitude.
"""

import io

import numpy as np
from PIL import Image

from proofloop.nisar.sme2 import BBox
from proofloop.world import World

# Colour ramp from low to high confidence (RGB), alpha rises with confidence.
LOW = np.array([253, 174, 97])
HIGH = np.array([215, 25, 28])
MIN_ALPHA, MAX_ALPHA = 110, 220


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
    alpha = np.where(flooded, MIN_ALPHA + (MAX_ALPHA - MIN_ALPHA) * t[..., 0], 0).astype(np.uint8)

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
