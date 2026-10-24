"""HTTP API for the web app.

uv run uvicorn proofloop.api.app:app --reload
"""

import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from proofloop.api.hazard_image import hazard_bounds, hazard_png
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


@app.post("/api/loop/demo")
def run_demo_loop(scenario: Scenario | None = None) -> Transcript:
    """Run the Loop on the hand-built World with rule-based agents."""
    return run_proofloop(demo_world(), scenario or DEMO_SCENARIO, DemoPlanner(), DemoAdversary())
