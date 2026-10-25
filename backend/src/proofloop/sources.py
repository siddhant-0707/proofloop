"""The curated source pack: what the Planner may cite and what every figure's evidence
points to. No runtime web search.

Each entry is a short paraphrase with its origin, so citations in a plan's
rationale can be traced. Add entries only from sources someone has read.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    origin: str
    summary: str


SOURCES: tuple[Source, ...] = (
    Source(
        id="S1",
        title="NISAR radar observation of Hurricane Isaias",
        origin="NASA-ISRO NISAR L2/L3 provisional products, track 148 frames 16 and 17 (ASF DAAC)",
        summary=(
            "NISAR imaged the Big Bend on Sep 28 and Oct 10, 2026, about a day after landfall. "
            "The hazard layer is radar-observed water change with a confidence per cell, "
            "not an official flood map."
        ),
    ),
    Source(
        id="S2",
        title="FEMA, Planning Considerations: Evacuation and Shelter-in-Place (2019)",
        origin="https://www.fema.gov/media-library/assets/documents/181495",
        summary=(
            "Evacuation is not all-or-nothing: a zone-phased approach moves as few people as "
            "necessary, and people not directly in harm's way can shelter in place, which "
            "reduces cost, resource needs and the harms of evacuation."
        ),
    ),
    Source(
        id="S3",
        title="Florida Statewide Emergency Shelter Plan (2020)",
        origin="Florida Division of Emergency Management",
        summary=(
            "Lists Dixie and Taylor counties' general-population shelters and their capacities: "
            "Dixie County High School (2,558 spaces) and Ruth Raines Middle School (1,523) in "
            "Cross City; Taylor County Elementary (3,503) and Taylor County High (3,151) in Perry."
        ),
    ),
    Source(
        id="S4",
        title="Cascade planning method",
        origin="Cascade method notes (docs/plan.md)",
        summary=(
            "People in flooded cells are affected. They can reach an open shelter through dry "
            "cells within a fixed travel distance. Each shelter takes at most its capacity, "
            "nearest people first, and nobody is counted twice. A closed road cuts a town off "
            "from shelters outside it; staged transport still reaches it. Transport and shelter "
            "costs are planning assumptions."
        ),
    ),
    Source(
        id="S5",
        title="FEMA National Flood Hazard Layer (NFHL) for Dixie and Taylor counties",
        origin="https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28",
        summary=(
            "Special Flood Hazard Areas (here zones A, AE, AH and VE) mark where FEMA expects "
            "flooding and flood insurance is usually required. People outside them often do "
            "not expect to flood and are less likely to be insured; most people in "
            "radar-flagged cells around Perry and Cross City live outside these zones."
        ),
    ),
    Source(
        id="S6",
        title="2020 Census block populations for Dixie and Taylor counties",
        origin=(
            "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/2"
        ),
        summary=(
            "Population of every 2020 Census block. Cascade spreads each block's people "
            "evenly over the cells it covers; it counts residents, not who was home during "
            "the storm."
        ),
    ),
)


def source(source_id: str) -> Source:
    return next(s for s in SOURCES if s.id == source_id)


def source_pack() -> str:
    return "\n".join(f"[{s.id}] {s.title} ({s.origin}): {s.summary}" for s in SOURCES)
