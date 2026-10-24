# ProofLoop

> Most AI tells you what to do. ProofLoop attacks its own plan until it survives.

ProofLoop helps a small county emergency manager build a hurricane response plan that has been stress-tested before anyone acts on it.
A Planner agent proposes a plan, an Adversary agent attacks it with realistic worst cases, and a deterministic simulation scores every plan against what actually flooded.
The flood truth comes from NASA-ISRO NISAR L-band radar, whose calibrated data became public in July 2026.
Our hero scenario is Hurricane Isaias (landfall Oct 9, 2026) in Florida's Big Bend, imaged by NISAR on Sep 28 (before) and Oct 10 (after).

Built at Gator Hack V (Oct 23-25, 2026).

## Repository layout

```
backend/   Python (uv): NISAR ingest, flood layers, simulation, verifier, agents, FastAPI
web/       Next.js + MapLibre: map, agent rounds, scenario sliders, evidence trail
docs/      Decisions and plan
data/      Downloaded and processed data (git-ignored)
```

## Setup

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 20+, curl, and a free [Earthdata Login](https://urs.earthdata.nasa.gov) stored in `~/.netrc`:

```
machine urs.earthdata.nasa.gov login <user> password <pass>
```

```bash
# NISAR data (priority 1: soil moisture ~0.4 GB, priority 2: frame 16 backscatter ~9.7 GB)
cd backend
uv run python -m proofloop.nisar.download --max-priority 1

# Build the cached Big Bend World (GCOV flood layer if downloaded, else SME2; downloads Census
# blocks on first run), then serve the API on :8000
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
cd web && npx tsc --noEmit && npm run lint
```

## Data

| Source | Use |
|---|---|
| NISAR L3 SME2 (soil moisture + gridded backscatter, 200 m) | Fallback hazard layer, wetting signal |
| NISAR L2 GCOV (backscatter, 10 m on frame 16, averaged to ~60 m) | Flood extent, including flooding under tree canopy |
| FEMA National Flood Hazard Layer | "Flooded outside the flood zone" |
| US Census block populations | People affected |
| County shelter lists | Plan resources |

See [docs/plan.md](docs/plan.md) for the agreed design.

## License

MIT
