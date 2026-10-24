"""Public hurricane shelters for Dixie and Taylor counties.

Capacities are the general-population risk capacities (spaces) summed over each
site's buildings in the 2020 Florida Statewide Emergency Shelter Plan:
  https://portal.floridadisaster.org/shelters/External/Current/2020%20SESP/Dixie.pdf
  https://portal.floridadisaster.org/shelters/External/Current/2020%20SESP/Taylor.pdf
Locations are the Census geocoder's match for each address.

The shelter plan has no cost to open. COST_PER_SPACE is a planning assumption
for a three-day activation (staff, cots, meals), not a published figure.
"""

from dataclasses import dataclass

COST_PER_SPACE = 25.0


@dataclass(frozen=True)
class ShelterSite:
    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    capacity: float

    @property
    def cost(self) -> float:
        return self.capacity * COST_PER_SPACE


SHELTER_SITES: tuple[ShelterSite, ...] = (
    # Dixie County HS buildings 1, 2, 3, 6, 7: 217 + 511 + 543 + 821 + 466.
    ShelterSite(
        "dixie-county-hs",
        "Dixie County High School",
        "17924 SE Hwy 19, Cross City",
        29.6247,
        -83.1089,
        2558,
    ),
    # Ruth Raines MS buildings 1, 2, 3, 5: 773 + 62 + 618 + 70.
    ShelterSite(
        "ruth-raines-ms",
        "Ruth Raines Middle School",
        "981 SE Hwy 351, Cross City",
        29.64819,
        -83.1233,
        1523,
    ),
    # Taylor County ES buildings 1-7: 250 + 276 + 796 + 401 + 438 + 875 + 467.
    ShelterSite(
        "taylor-county-es",
        "Taylor County Elementary School",
        "1600 E Green St, Perry",
        30.11721,
        -83.56814,
        3503,
    ),
    # Taylor County HS buildings 1A, 2B, 3C, 4D: 2530 + 268 + 209 + 144.
    ShelterSite(
        "taylor-county-hs",
        "Taylor County High School",
        "900 N Johnson Stripling Rd, Perry",
        30.12482,
        -83.57505,
        3151,
    ),
)
