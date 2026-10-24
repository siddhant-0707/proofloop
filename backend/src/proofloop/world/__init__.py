"""The World: everything the Simulation needs, precomputed and immutable.

All per-cell arrays share the grid's (rows, cols) shape. Row 0 is the
northernmost row and column 0 the westernmost.
"""

from dataclasses import dataclass
from enum import IntEnum

import numpy as np


@dataclass(frozen=True)
class Grid:
    latitude: np.ndarray  # (rows,) cell-center latitudes, north to south
    longitude: np.ndarray  # (cols,) cell-center longitudes, west to east

    @property
    def shape(self) -> tuple[int, int]:
        return (self.latitude.size, self.longitude.size)


class FloodKind(IntEnum):
    NONE = 0
    OPEN_WATER = 1  # backscatter darkened: smooth water surface
    UNDER_CANOPY = 2  # backscatter brightened: double bounce off water under vegetation


@dataclass(frozen=True)
class HazardLayer:
    flooded: np.ndarray  # (rows, cols) bool
    confidence: np.ndarray  # (rows, cols) float in [0, 1]
    method: str  # how the layer was derived, e.g. "sme2" or "gcov"
    # (rows, cols) uint8 FloodKind per cell, or None when the method cannot tell them apart.
    kind: np.ndarray | None = None


@dataclass(frozen=True)
class Shelter:
    id: str
    name: str
    row: int
    col: int
    capacity: float
    cost: float


# Compared and hashed by identity, so per-World results (shelter reachability) can be cached.
@dataclass(frozen=True, eq=False)
class World:
    grid: Grid
    hazard: HazardLayer
    population: np.ndarray  # (rows, cols) people per cell
    shelters: tuple[Shelter, ...] = ()
    # How far people can travel to a shelter, in 4-connected cell steps.
    reach_cells: int = 25

    def shelter(self, shelter_id: str) -> Shelter | None:
        return next((s for s in self.shelters if s.id == shelter_id), None)
