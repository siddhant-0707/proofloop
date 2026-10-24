"""Cache a World on disk so the API never reads multi-gigabyte HDF5 granules."""

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from proofloop.world import Grid, HazardLayer, Shelter, World


def save_world(world: World, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "method": world.hazard.method,
        "reach_cells": world.reach_cells,
        "shelters": [asdict(s) for s in world.shelters],
    }
    with path.open("wb") as f:
        np.savez_compressed(
            f,
            latitude=world.grid.latitude,
            longitude=world.grid.longitude,
            flooded=world.hazard.flooded,
            confidence=world.hazard.confidence,
            population=world.population,
            meta=np.array(json.dumps(meta)),
        )


def load_world(path: Path) -> World:
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(str(data["meta"]))
        return World(
            grid=Grid(latitude=data["latitude"], longitude=data["longitude"]),
            hazard=HazardLayer(
                flooded=data["flooded"], confidence=data["confidence"], method=meta["method"]
            ),
            population=data["population"],
            shelters=tuple(Shelter(**s) for s in meta["shelters"]),
            reach_cells=meta["reach_cells"],
        )
