"""HTTP API for the web app.

uv run uvicorn proofloop.api.app:app --reload
"""

import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from proofloop.api.hazard_image import hazard_bounds, hazard_png, population_png
from proofloop.loop import Scenario, Transcript, run_proofloop
from proofloop.loop.demo import DEMO_SCENARIO, DemoAdversary, DemoPlanner, demo_world
from proofloop.paths import WORLD_CACHE
from proofloop.world import FloodKind, World
from proofloop.world.store import load_world

app = FastAPI(title="ProofLoop")


class Bounds(BaseModel):
    west: float
    south: float
    east: float
    north: float


class HazardLayerInfo(BaseModel):
    method: str
    bounds: Bounds
    rows: int
    cols: int
    flagged_cells: int
    # Null when the hazard method cannot tell open water from flooding under canopy.
    open_water_cells: int | None
    under_canopy_cells: int | None
    image_url: str


class ShelterInfo(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    capacity: float
    cost: float


class ExposureInfo(BaseModel):
    total_population: float
    people_in_flooded_cells: float
    population_image_url: str
    shelters: list[ShelterInfo]


# Enough to open two of the four shelters; sliders will edit this base scenario.
BIG_BEND_SCENARIO = Scenario(budget=150_000)


@lru_cache(maxsize=1)
def big_bend_world() -> World:
    path = Path(os.environ.get("PROOFLOOP_WORLD", WORLD_CACHE))
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"World cache {path} not found; run: uv run python -m proofloop.world.build",
        )
    return load_world(path)


@app.get("/api/hazard")
def hazard() -> HazardLayerInfo:
    world = big_bend_world()
    rows, cols = world.grid.shape
    kind = world.hazard.kind
    return HazardLayerInfo(
        method=world.hazard.method,
        bounds=Bounds(**asdict(hazard_bounds(world))),
        rows=rows,
        cols=cols,
        flagged_cells=int(world.hazard.flooded.sum()),
        open_water_cells=None if kind is None else int((kind == FloodKind.OPEN_WATER).sum()),
        under_canopy_cells=None if kind is None else int((kind == FloodKind.UNDER_CANOPY).sum()),
        image_url="/api/hazard.png",
    )


@app.get("/api/hazard.png")
def hazard_image() -> Response:
    return Response(
        content=_hazard_png_bytes(), media_type="image/png", headers={"Cache-Control": "no-cache"}
    )


@lru_cache(maxsize=1)
def _hazard_png_bytes() -> bytes:
    return hazard_png(big_bend_world())


@app.get("/api/exposure")
def exposure() -> ExposureInfo:
    world = big_bend_world()
    lat, lon = world.grid.latitude, world.grid.longitude
    return ExposureInfo(
        total_population=float(world.population.sum()),
        people_in_flooded_cells=float(world.population[world.hazard.flooded].sum()),
        population_image_url="/api/population.png",
        shelters=[
            ShelterInfo(
                id=s.id,
                name=s.name,
                latitude=float(lat[s.row]),
                longitude=float(lon[s.col]),
                capacity=s.capacity,
                cost=s.cost,
            )
            for s in world.shelters
        ],
    )


@app.get("/api/population.png")
def population_image() -> Response:
    return Response(
        content=_population_png_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@lru_cache(maxsize=1)
def _population_png_bytes() -> bytes:
    return population_png(big_bend_world())


@app.post("/api/loop")
def run_loop(scenario: Scenario | None = None) -> Transcript:
    """Run the Loop on the real Big Bend World with rule-based agents."""
    world = big_bend_world()
    return run_proofloop(world, scenario or BIG_BEND_SCENARIO, DemoPlanner(), DemoAdversary())


@app.post("/api/loop/demo")
def run_demo_loop(scenario: Scenario | None = None) -> Transcript:
    """Run the Loop on the hand-built World with rule-based agents."""
    return run_proofloop(demo_world(), scenario or DEMO_SCENARIO, DemoPlanner(), DemoAdversary())
