"""HTTP API for the web app.

uv run uvicorn proofloop.api.app:app --reload
"""

import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from proofloop.api.hazard_image import hazard_bounds, hazard_png
from proofloop.gemma.agents import GemmaAdversary, GemmaPlanner
from proofloop.gemma.client import GemmaClient
from proofloop.gemma.providers import providers_from_env
from proofloop.loop import Scenario, Transcript, run_proofloop
from proofloop.loop.demo import DEMO_SCENARIO, DemoAdversary, DemoPlanner, demo_world
from proofloop.paths import BACKEND_DIR, WORLD_CACHE
from proofloop.world import World
from proofloop.world.store import load_world

# Variables already set in the shell win over backend/.env.
load_dotenv(BACKEND_DIR / ".env", override=False)

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
    return HazardLayerInfo(
        method=world.hazard.method,
        bounds=Bounds(**asdict(hazard_bounds(world))),
        rows=rows,
        cols=cols,
        flagged_cells=int(world.hazard.flooded.sum()),
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


@app.post("/api/loop/gemma")
def run_gemma_loop(scenario: Scenario | None = None) -> Transcript:
    """Run the Loop on the demo World with Gemma 4 as Planner and Adversary."""
    providers = providers_from_env()
    if not providers:
        raise HTTPException(
            status_code=503, detail="Set GEMINI_API_KEY and/or OPENROUTER_API_KEY in backend/.env"
        )
    client = GemmaClient(providers)
    return run_proofloop(
        demo_world(), scenario or DEMO_SCENARIO, GemmaPlanner(client), GemmaAdversary(client)
    )
