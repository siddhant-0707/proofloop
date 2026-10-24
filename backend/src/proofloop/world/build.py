"""Build and cache the Big Bend World from downloaded NISAR SME2 granules.

uv run python -m proofloop.world.build
"""

from proofloop.nisar.manifest import GRANULES
from proofloop.nisar.sme2 import BBox
from proofloop.paths import RAW_NISAR_DIR, WORLD_CACHE
from proofloop.world.builder import build_world_from_sme2
from proofloop.world.store import save_world

# Dixie County and coastal Taylor County, inside track 148 frame 16.
BIG_BEND = BBox(west=-83.75, south=29.3, east=-82.9, north=30.05)
FRAME = 16


def main() -> None:
    sme2 = {
        g.epoch: RAW_NISAR_DIR / g.filename
        for g in GRANULES
        if g.product == "SME2" and g.frame == FRAME
    }
    missing = [p.name for p in sme2.values() if not p.exists()]
    if missing:
        raise SystemExit(
            f"missing {missing}; run: uv run python -m proofloop.nisar.download --max-priority 1"
        )

    world = build_world_from_sme2(sme2["before"], sme2["after"], BIG_BEND)
    save_world(world, WORLD_CACHE)
    rows, cols = world.grid.shape
    print(f"wrote {WORLD_CACHE} ({rows}x{cols} cells, {int(world.hazard.flooded.sum())} flagged)")


if __name__ == "__main__":
    main()
