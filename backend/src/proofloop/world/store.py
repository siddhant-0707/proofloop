"""Cache a World on disk so the API never reads multi-gigabyte HDF5 granules."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from proofloop.world import Community, Grid, HazardLayer, Shelter, World


def save_world(world: World, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "method": world.hazard.method,
        "reach_cells": world.reach_cells,
        "shelters": [asdict(s) for s in world.shelters],
        "communities": [asdict(c) for c in world.communities],
        "transport_cost_per_seat": world.transport_cost_per_seat,
    }
    arrays: dict[str, Any] = {
        "latitude": world.grid.latitude,
        "longitude": world.grid.longitude,
        "flooded": world.hazard.flooded,
        "confidence": world.hazard.confidence,
        "population": world.population,
    }
    if world.hazard.kind is not None:
        arrays["kind"] = world.hazard.kind
    with path.open("wb") as f:
        np.savez_compressed(f, meta=np.array(json.dumps(meta)), **arrays)


def load_world(path: Path) -> World:
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(str(data["meta"]))
        return World(
            grid=Grid(latitude=data["latitude"], longitude=data["longitude"]),
            hazard=HazardLayer(
                flooded=data["flooded"],
                confidence=data["confidence"],
                method=meta["method"],
                kind=data["kind"] if "kind" in data else None,
            ),
            population=data["population"],
            shelters=tuple(Shelter(**s) for s in meta["shelters"]),
            reach_cells=meta["reach_cells"],
            communities=tuple(Community(**c) for c in meta.get("communities", [])),
            transport_cost_per_seat=meta.get(
                "transport_cost_per_seat", World.transport_cost_per_seat
            ),
        )
