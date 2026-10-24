"""Build and cache the Big Bend World from downloaded NISAR granules and Census blocks.

Uses the GCOV flood layer when both frame 16 GCOV granules are fully downloaded,
otherwise the SME2 fallback. Downloads Census blocks on first run.

uv run python -m proofloop.world.build
"""

from proofloop.exposure.census import block_files, download_blocks, load_blocks
from proofloop.exposure.shelters import SHELTER_SITES
from proofloop.nisar.manifest import GRANULES, Product
from proofloop.nisar.sme2 import BBox
from proofloop.paths import RAW_NISAR_DIR, WORLD_CACHE
from proofloop.world.builder import GranulePair, build_world, with_exposure
from proofloop.world.store import save_world

# Dixie County and coastal Taylor County inside track 148 frame 16, plus Perry to the
# north, where Taylor County's shelters are. Frame 16 has no radar samples over Perry.
BIG_BEND = BBox(west=-83.75, south=29.3, east=-82.9, north=30.15)
FRAME = 16


def main() -> None:
    sme2, gcov = _downloaded("SME2"), _downloaded("GCOV")
    if sme2 is None:
        raise SystemExit(
            "missing SME2 granules; run: uv run python -m proofloop.nisar.download --max-priority 1"
        )
    if gcov is None:
        print("GCOV granules not downloaded; falling back to SME2 (--max-priority 2 to fetch)")

    if not all(p.exists() for p in block_files()):
        print("downloading Census blocks")
        download_blocks()
    blocks = [block for path in block_files() for block in load_blocks(path)]

    world = with_exposure(build_world(BIG_BEND, sme2, gcov), blocks, SHELTER_SITES)
    save_world(world, WORLD_CACHE)
    rows, cols = world.grid.shape
    affected = world.population[world.hazard.flooded].sum()
    print(
        f"wrote {WORLD_CACHE} ({world.hazard.method}, {rows}x{cols} cells, "
        f"{int(world.hazard.flooded.sum())} flagged, {world.population.sum():,.0f} people, "
        f"{affected:,.0f} in flagged cells, {len(world.shelters)} shelters)"
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
