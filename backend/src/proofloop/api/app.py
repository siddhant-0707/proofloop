"""HTTP API for the web app.

uv run uvicorn proofloop.api.app:app --reload
"""

import json
import os
import queue
import threading
from collections.abc import Callable
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from proofloop.api.hazard_image import hazard_bounds, hazard_png, population_png
from proofloop.gemma.agents import GemmaAdversary, GemmaPlanner
from proofloop.gemma.client import GemmaClient
from proofloop.gemma.providers import providers_from_env
from proofloop.loop import (
    DEFAULT_ROUNDS,
    Adversary,
    Planner,
    Round,
    Scenario,
    Transcript,
    run_proofloop,
)
from proofloop.loop.demo import DEMO_SCENARIO, DemoAdversary, DemoPlanner, demo_world
from proofloop.paths import BACKEND_DIR, WORLD_CACHE
from proofloop.world import FloodKind, World
from proofloop.world.store import load_world

# Variables already set in the shell win over backend/.env.
load_dotenv(BACKEND_DIR / ".env", override=False)

app = FastAPI(title="ProofLoop")
app.add_middleware(GZipMiddleware, minimum_size=1000)


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


class FloodCells(BaseModel):
    kinds: dict[int, str]  # FloodKind value -> name; 0 when the method cannot tell kinds apart
    cells: list[list[float]]  # [lon, lat, kind, confidence, people] per flagged cell


class ShelterInfo(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    capacity: float
    cost: float


class CommunityInfo(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float


class ExposureInfo(BaseModel):
    total_population: float
    people_in_flooded_cells: float
    population_image_url: str
    shelters: list[ShelterInfo]
    communities: list[CommunityInfo]


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


@app.get("/api/flood-cells")
def flood_cells() -> FloodCells:
    """Every flagged cell as [lon, lat, kind, confidence, people], for vector rendering."""
    world = big_bend_world()
    rows, cols = np.nonzero(world.hazard.flooded)
    kind = world.hazard.kind
    kinds = kind[rows, cols] if kind is not None else np.zeros(rows.size, dtype=np.uint8)
    cells = np.column_stack(
        [
            world.grid.longitude[cols].round(5),
            world.grid.latitude[rows].round(5),
            kinds,
            world.hazard.confidence[rows, cols].round(2),
            world.population[rows, cols].round(1),
        ]
    )
    return FloodCells(kinds={int(k): k.name.lower() for k in FloodKind}, cells=cells.tolist())


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
        communities=[
            CommunityInfo(
                id=c.id, name=c.name, latitude=float(lat[c.row]), longitude=float(lon[c.col])
            )
            for c in world.communities
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
    return _run_big_bend(scenario, *_agents("rules"))


@app.post("/api/loop/demo")
def run_demo_loop(scenario: Scenario | None = None) -> Transcript:
    """Run the Loop on the hand-built World with rule-based agents."""
    return run_proofloop(demo_world(), scenario or DEMO_SCENARIO, DemoPlanner(), DemoAdversary())


@app.post("/api/loop/gemma")
def run_gemma_loop(scenario: Scenario | None = None) -> Transcript:
    """Run the Loop on the real Big Bend World with Gemma 4 as Planner and Adversary."""
    return _run_big_bend(scenario, *_agents("gemma"))


AgentKind = Literal["gemma", "rules"]


@app.post("/api/loop/stream")
def stream_loop(agents: AgentKind = "gemma", scenario: Scenario | None = None) -> StreamingResponse:
    """Run the Loop on the Big Bend World, streaming one JSON event per line.

    Events: {"type": "started", "rounds": n}, then {"type": "round", "round": ...} as each
    round completes, then {"type": "transcript", "transcript": ...} or {"type": "error"}.
    """
    planner, adversary = _agents(agents)  # fails with 503 before streaming starts
    events: queue.Queue[dict | None] = queue.Queue()

    def work() -> None:
        try:
            transcript = _run_big_bend(
                scenario,
                planner,
                adversary,
                on_round=lambda r: events.put(
                    {"type": "round", "round": r.model_dump(mode="json")}
                ),
            )
            events.put({"type": "transcript", "transcript": transcript.model_dump(mode="json")})
        except Exception as error:  # noqa: BLE001 - reported to the client as an event
            events.put({"type": "error", "detail": f"{type(error).__name__}: {error}"})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def lines():
        yield json.dumps({"type": "started", "rounds": DEFAULT_ROUNDS}) + "\n"
        while (event := events.get()) is not None:
            yield json.dumps(event) + "\n"

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _agents(kind: AgentKind) -> tuple[Planner, Adversary]:
    if kind == "rules":
        return DemoPlanner(), DemoAdversary()
    providers = providers_from_env()
    if not providers:
        raise HTTPException(
            status_code=503,
            detail="Gemma is not configured: set OPENROUTER_API_KEY and/or GEMINI_API_KEY "
            "in backend/.env",
        )
    client = GemmaClient(providers)
    return GemmaPlanner(client), GemmaAdversary(client)


def _run_big_bend(
    scenario: Scenario | None,
    planner: Planner,
    adversary: Adversary,
    on_round: Callable[[Round], None] | None = None,
) -> Transcript:
    return run_proofloop(
        big_bend_world(), scenario or BIG_BEND_SCENARIO, planner, adversary, on_round=on_round
    )
