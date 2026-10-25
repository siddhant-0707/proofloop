"""Communities in the Big Bend that transport and road closures act on.

Each is a town center and a radius covering its built-up area. Centers are
approximate town coordinates (to within a few hundred meters), not surveyed
points; the 4 km radius is a planning assumption.
"""

from dataclasses import dataclass

RADIUS_M = 4_000.0


@dataclass(frozen=True)
class CommunitySite:
    id: str
    name: str
    latitude: float
    longitude: float
    radius_m: float = RADIUS_M


COMMUNITY_SITES: tuple[CommunitySite, ...] = (
    CommunitySite("keaton-beach", "Keaton Beach", 29.8183, -83.5940),
    CommunitySite("steinhatchee", "Steinhatchee", 29.6711, -83.3876),
    CommunitySite("horseshoe-beach", "Horseshoe Beach", 29.4410, -83.2868),
    CommunitySite("suwannee", "Suwannee", 29.3253, -83.1462),
    CommunitySite("cross-city", "Cross City", 29.6344, -83.1252),
    CommunitySite("perry", "Perry", 30.1172, -83.5818),
)
