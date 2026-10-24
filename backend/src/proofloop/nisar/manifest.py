"""NISAR granules for the Hurricane Isaias hindcast (Big Bend, Florida).

Track 148 ascending, frames 16 (Dixie and coastal Taylor County) and 17
(Perry, Tallahassee). Before pass 2026-09-28, after pass 2026-10-10, about
one day after landfall. URLs and sizes were validated against ASF on
2026-10-24.
"""

from dataclasses import dataclass
from typing import Literal

Product = Literal["SME2", "GCOV"]
Epoch = Literal["before", "after"]

_BASE = "https://nisar.asf.earthdatacloud.nasa.gov/NISAR"
_COLLECTION = {
    "SME2": "NISAR_L3_SME2_PROVISIONAL_V1",
    "GCOV": "NISAR_L2_GCOV_PROVISIONAL_V1",
}
_LEVEL = {"SME2": "L3", "GCOV": "L2"}
_PASS = {
    # (frame, epoch) -> (cycle, start, stop)
    (16, "before"): ("031", "20260928T105331", "20260928T105405"),
    (16, "after"): ("032", "20261010T105331", "20261010T105405"),
    (17, "before"): ("031", "20260928T105404", "20260928T105439"),
    (17, "after"): ("032", "20261010T105404", "20261010T105439"),
}


@dataclass(frozen=True)
class Granule:
    product: Product
    frame: int
    epoch: Epoch
    size_bytes: int
    priority: int

    @property
    def name(self) -> str:
        cycle, start, stop = _PASS[(self.frame, self.epoch)]
        return (
            f"NISAR_{_LEVEL[self.product]}_PR_{self.product}_{cycle}_148_A_"
            f"{self.frame:03d}_4005_DHDH_A_{start}_{stop}_P05023_N_F_J_001"
        )

    @property
    def filename(self) -> str:
        return f"{self.name}.h5"

    @property
    def url(self) -> str:
        return f"{_BASE}/{_COLLECTION[self.product]}/{self.name}/{self.filename}"


GRANULES: tuple[Granule, ...] = (
    # Priority 1: soil moisture, small and analysis-ready (fallback hazard layer).
    Granule("SME2", 16, "before", 77_594_624, 1),
    Granule("SME2", 16, "after", 75_497_472, 1),
    Granule("SME2", 17, "before", 121_634_816, 1),
    Granule("SME2", 17, "after", 119_537_664, 1),
    # Backscatter. Optional: world.build fetches a Big Bend crop of any granule not downloaded.
    # Priority 2: Dixie County and the coast.
    Granule("GCOV", 16, "before", 4_857_004_032, 2),
    Granule("GCOV", 16, "after", 4_861_198_336, 2),
    # Priority 3: Perry, inland Taylor County and Tallahassee.
    Granule("GCOV", 17, "before", 6_534_725_632, 3),
    Granule("GCOV", 17, "after", 6_526_337_024, 3),
)
