# Cascade

> Most AI tells you what to do. Cascade attacks its own plan until it survives.

Cascade (formerly ProofLoop) helps a small county emergency manager build a hurricane response plan that has been stress-tested before anyone acts on it.
A Planner agent proposes a plan, an Adversary agent attacks it with realistic worst cases, and a deterministic simulation scores every plan against what actually flooded.
The flood truth comes from NASA-ISRO NISAR L-band radar, whose calibrated data became public in July 2026.
Our hero scenario is Hurricane Isaias (landfall Oct 9, 2026) in Florida's Big Bend, imaged by NISAR on Sep 28 (before) and Oct 10 (after).

Built at Gator Hack V (Oct 23-25, 2026).

## Repository layout

```
backend/   Python (uv): NISAR ingest, flood layers, simulation, verifier, agents, FastAPI
web/       Next.js + MapLibre: map, run progress, plan report, evidence trail
docs/      Decisions and plan
data/      Downloaded and processed data (git-ignored)
```

## Setup

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 20+, curl, and a free [Earthdata Login](https://urs.earthdata.nasa.gov) stored in `~/.netrc`:

```
machine urs.earthdata.nasa.gov login <user> password <pass>
```

```bash
# NISAR data (priority 1: soil moisture ~0.4 GB; full backscatter granules are optional)
cd backend
uv run python -m proofloop.nisar.download --max-priority 1

# Gemma 4 agents: put API keys in backend/.env (git-ignored). OpenRouter is the primary
# provider and the Gemini API the fallback; set at least one.
#   OPENROUTER_API_KEY=sk-or-...
#   GEMINI_API_KEY=...

# Build the cached Big Bend World, then serve the API on :8000. The GCOV flood layer mosaics
# frames 16 and 17; any granule not downloaded is read as a Big Bend crop over HTTP range
# requests (~300 MB each, cached in data/raw/nisar/crops). Census blocks download on first run.
uv run python -m proofloop.world.build
uv run uvicorn proofloop.api.app:app --reload

# Web on :3000 (proxies /api to the backend; override with PROOFLOOP_API)
cd ../web
npm install
npm run dev
```

Checks:

```bash
cd backend && uv run pytest && uv run pyright && uv run ruff check . && uv run ruff format --check .
cd web && npx tsc --noEmit && npm run lint && npm test
```

## API

| Route | What it does |
|---|---|
| `GET /api/hazard`, `/api/hazard.png` | Hazard layer metadata and map image |
| `GET /api/exposure`, `/api/population.png` | Population, shelters, communities, and the population image |
| `GET /api/fema-zones.png` | FEMA Special Flood Hazard Area as a map image |
| `POST /api/loop/stream?agents=gemma\|rules&rounds=1-3` | Run the Loop on the Big Bend World for the Scenario in the body, streaming one JSON event per line (`started`, each `round`, then `transcript` or `error`); the web app uses `rounds=1` to re-plan |
| `POST /api/loop/gemma` | Run the Loop on the Big Bend World with Gemma 4 as Planner and Adversary |
| `POST /api/loop` | Run the Loop on the Big Bend World with rule-based agents |
| `POST /api/loop/demo` | Run the Loop on the fictional demo county with rule-based agents |

## Data

| Source | Use |
|---|---|
| NISAR L3 SME2 (soil moisture + gridded backscatter, 200 m) | Fallback hazard layer, wetting signal |
| NISAR L2 GCOV (backscatter, 10 m on frames 16 and 17, averaged to ~60 m) | Flood extent, including flooding under tree canopy |
| FEMA National Flood Hazard Layer | "Flooded outside the flood zone" |
| US Census block populations | People affected |
| County shelter lists | Plan resources |

See [docs/plan.md](docs/plan.md) for the agreed design.

## License

MIT
