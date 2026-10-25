"""Small hand-drawn Worlds and agent responses for Loop tests.

Worlds are drawn as small maps:
    ~  flooded cell holding `pop` affected people, inside a FEMA flood zone
    o  flooded cell holding `pop` affected people, outside any FEMA flood zone (map only:
       planning counts both the same)
    .  dry, passable cell
    A-Z shelter on a dry cell
"""

import numpy as np

from proofloop.world import Community, Grid, HazardLayer, Shelter, World

TRANSPORT_COST_PER_SEAT = 150.0


def world_from_map(
    rows: list[str], pop: float = 10.0, shelters=None, communities=None, reach_cells: int = 25
) -> World:
    """shelters maps a letter to (capacity, cost); communities maps an id to (row, col, radius)."""
    shelters = shelters or {}
    communities = communities or {}
    flooded = np.array([[ch in "~o" for ch in row] for row in rows])
    in_fema_zone = np.array([[ch == "~" for ch in row] for row in rows])
    n_rows, n_cols = flooded.shape
    return World(
        grid=Grid(
            latitude=np.linspace(30.0, 29.9, n_rows),
            longitude=np.linspace(-83.5, -83.4, n_cols),
        ),
        hazard=HazardLayer(
            flooded=flooded,
            confidence=np.where(flooded, 1.0, 0.0),
            method="hand-built",
        ),
        population=np.where(flooded, pop, 0.0),
        shelters=tuple(
            Shelter(id=ch, name=f"Shelter {ch}", row=r, col=c, capacity=cap, cost=cost)
            for r, row in enumerate(rows)
            for c, ch in enumerate(row)
            if ch in shelters
            for cap, cost in [shelters[ch]]
        ),
        communities=tuple(
            Community(id=cid, name=f"Town {cid}", row=r, col=c, radius_cells=radius)
            for cid, (r, c, radius) in communities.items()
        ),
        reach_cells=reach_cells,
        transport_cost_per_seat=TRANSPORT_COST_PER_SEAT,
        in_fema_zone=in_fema_zone,
    )


def open_plan(*shelter_ids: str, cost: float, sheltered: float) -> dict:
    return {
        "actions": [{"type": "open_shelter", "shelter_id": s} for s in shelter_ids],
        "claims": {"cost": cost, "people_sheltered": sheltered},
        "rationale": "test plan",
    }


def offline(shelter_id: str) -> dict:
    return {"type": "shelter_offline", "shelter_id": shelter_id}


def plan(*actions: dict, cost: float, sheltered: float) -> dict:
    return {
        "actions": list(actions),
        "claims": {"cost": cost, "people_sheltered": sheltered},
        "rationale": "test plan",
    }


def open_shelter(shelter_id: str) -> dict:
    return {"type": "open_shelter", "shelter_id": shelter_id}


def transport(community_id: str, seats: int) -> dict:
    return {"type": "stage_transport", "community_id": community_id, "seats": seats}


def reserve(amount: float) -> dict:
    return {"type": "allocate_budget", "category": "contingency_reserve", "amount": amount}


def road_closed(community_id: str) -> dict:
    return {"type": "road_closed", "community_id": community_id}


def budget_cut(percent: float) -> dict:
    return {"type": "budget_cut", "percent": percent}
