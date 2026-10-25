"""Build and cache the Big Bend World from NISAR granules and Census blocks.

The GCOV flood layer mosaics frames 16 and 17. Each GCOV granule is read from the full
download when present, otherwise from a crop over the Big Bend fetched once with HTTP
range requests (a few hundred MB instead of 5 to 7 GB). Falls back to SME2 if a crop
cannot be fetched. Downloads Census blocks on first run.

uv run python -m proofloop.world.build
"""

import subprocess
import time
import urllib.error
from pathlib import Path

from proofloop.exposure.census import block_files, download_blocks, load_blocks
from proofloop.exposure.communities import COMMUNITY_SITES
from proofloop.exposure.fema import cached_for, download_zones, load_zones, zones_file
from proofloop.exposure.shelters import SHELTER_SITES
from proofloop.nisar.gcov import read_gcov, write_gcov_crop
from proofloop.nisar.manifest import GRANULES, Granule, Product
from proofloop.nisar.remote import RemoteFile, signed_url
from proofloop.nisar.sme2 import BBox
from proofloop.paths import NISAR_CROPS_DIR, RAW_NISAR_DIR, WORLD_CACHE
from proofloop.world.builder import (
    GCOV_CELL_M,
    GranulePair,
    build_world,
    with_communities,
    with_exposure,
    with_flood_zones,
)
from proofloop.world.store import save_world

# Dixie County and Taylor County from the coast north through Perry, where Taylor County's
# shelters are. Frame 16 covers the coast and Dixie County, frame 17 Perry.
BIG_BEND = BBox(west=-83.75, south=29.3, east=-82.9, north=30.15)
FRAMES = (16, 17)
# Room for the builder's own padding around the bbox.
CROP_PAD_M = 2 * GCOV_CELL_M


def main() -> None:
    sme2 = [_downloaded("SME2", frame) for frame in FRAMES]
    if any(pair is None for pair in sme2):
        raise SystemExit(
            "missing SME2 granules; run: uv run python -m proofloop.nisar.download --max-priority 1"
        )
    try:
        gcov = [_gcov_pair(frame) for frame in FRAMES]
    except (subprocess.CalledProcessError, urllib.error.URLError, OSError) as error:
        print(f"could not fetch GCOV crops ({error}); falling back to SME2")
        gcov = []

    if not all(p.exists() for p in block_files()):
        print("downloading Census blocks")
        download_blocks()
    blocks = [block for path in block_files() for block in load_blocks(path)]

    pairs = [pair for pair in sme2 if pair is not None]
    world = with_exposure(build_world(BIG_BEND, pairs, gcov), blocks, SHELTER_SITES)
    world = with_communities(world, COMMUNITY_SITES)
    if not cached_for(BIG_BEND):
        print("downloading FEMA flood zones")
        download_zones(BIG_BEND)
    world = with_flood_zones(world, load_zones(zones_file()))
    save_world(world, WORLD_CACHE)
    rows, cols = world.grid.shape
    affected = world.population[world.hazard.flooded].sum()
    print(
        f"wrote {WORLD_CACHE} ({world.hazard.method}, {rows}x{cols} cells, "
        f"{int(world.hazard.flooded.sum())} flagged, {world.population.sum():,.0f} people, "
        f"{affected:,.0f} in flagged cells, {len(world.shelters)} shelters, "
        f"{len(world.communities)} communities)"
    )


def _downloaded(product: Product, frame: int) -> GranulePair | None:
    """The frame's before/after pair, or None unless both are completely downloaded."""
    paths = {}
    for g in _granules(product, frame):
        if not _is_complete(g):
            return None
        paths[g.epoch] = RAW_NISAR_DIR / g.filename
    return GranulePair(before=paths["before"], after=paths["after"])


def _gcov_pair(frame: int) -> GranulePair:
    paths = {g.epoch: _gcov_source(g) for g in _granules("GCOV", frame)}
    return GranulePair(before=paths["before"], after=paths["after"])


def _gcov_source(granule: Granule) -> Path:
    """The full granule if downloaded, otherwise its Big Bend crop, fetched if missing."""
    if _is_complete(granule):
        return RAW_NISAR_DIR / granule.filename
    b = BIG_BEND
    crop = NISAR_CROPS_DIR / f"{granule.name}_{b.west}_{b.south}_{b.east}_{b.north}.h5"
    if not crop.exists():
        print(f"fetch {granule.name} crop over the Big Bend (range requests)")
        start = time.monotonic()
        remote = RemoteFile(signed_url(granule, RAW_NISAR_DIR / ".urs_cookies"))
        write_gcov_crop(read_gcov(remote, BIG_BEND, CROP_PAD_M, layers=("hh",)), crop)
        print(
            f"      {remote.fetched_bytes / 1e6:.0f} MB in {time.monotonic() - start:.0f} s, "
            f"saved {crop.stat().st_size / 1e6:.0f} MB"
        )
    return crop


def _granules(product: Product, frame: int) -> list[Granule]:
    return [g for g in GRANULES if g.product == product and g.frame == frame]


def _is_complete(granule: Granule) -> bool:
    path = RAW_NISAR_DIR / granule.filename
    return path.is_file() and path.stat().st_size == granule.size_bytes


if __name__ == "__main__":
    main()
