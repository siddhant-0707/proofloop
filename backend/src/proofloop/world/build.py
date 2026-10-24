"""Build and cache the Big Bend World from downloaded NISAR granules.

Uses the GCOV flood layer when both frame 16 GCOV granules are fully downloaded,
otherwise the SME2 fallback.

uv run python -m proofloop.world.build
"""

from proofloop.nisar.manifest import GRANULES, Product
from proofloop.nisar.sme2 import BBox
from proofloop.paths import RAW_NISAR_DIR, WORLD_CACHE
from proofloop.world.builder import GranulePair, build_world
from proofloop.world.store import save_world

# Dixie County and coastal Taylor County, inside track 148 frame 16.
BIG_BEND = BBox(west=-83.75, south=29.3, east=-82.9, north=30.05)
FRAME = 16


def main() -> None:
    sme2, gcov = _downloaded("SME2"), _downloaded("GCOV")
    if sme2 is None:
        raise SystemExit(
            "missing SME2 granules; run: uv run python -m proofloop.nisar.download --max-priority 1"
        )
    if gcov is None:
        print("GCOV granules not downloaded; falling back to SME2 (--max-priority 2 to fetch)")

    world = build_world(BIG_BEND, sme2, gcov)
    save_world(world, WORLD_CACHE)
    rows, cols = world.grid.shape
    print(
        f"wrote {WORLD_CACHE} ({world.hazard.method}, {rows}x{cols} cells, "
        f"{int(world.hazard.flooded.sum())} flagged)"
    )


def _downloaded(product: Product) -> GranulePair | None:
    """The frame's before/after pair, or None unless both are completely downloaded."""
    paths = {}
    for g in GRANULES:
        if g.product == product and g.frame == FRAME:
            path = RAW_NISAR_DIR / g.filename
            if not path.is_file() or path.stat().st_size != g.size_bytes:
                return None
            paths[g.epoch] = path
    return GranulePair(before=paths["before"], after=paths["after"])


if __name__ == "__main__":
    main()
