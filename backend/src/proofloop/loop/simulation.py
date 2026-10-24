"""Deterministic scoring of a Plan against a World under a Scenario. No randomness, no LLM.

People in flooded cells are affected. An affected cell can reach an open shelter
when a 4-connected path from it to the shelter, at most `world.reach_cells` steps
long, crosses only dry cells after leaving the starting cell. Each shelter fills
its capacity with the nearest reachable people first; shelters are filled in
plan order and ties break by row, then column.
"""

from functools import lru_cache

import numpy as np

from proofloop.loop.schemas import Plan, Scenario, SimulationResult
from proofloop.world import Shelter, World

_UNREACHED = np.iinfo(np.int32).max // 2


def simulate(world: World, scenario: Scenario, plan: Plan) -> SimulationResult:
    affected = np.where(world.hazard.flooded, world.population, 0.0)
    remaining = affected.copy()
    cost = 0.0

    for shelter in _opened_shelters(world, plan):
        cost += shelter.cost
        if shelter.id in scenario.offline_shelters:
            continue
        rows, cols = _reachable_cells(world, shelter)
        people = remaining[rows, cols]
        ahead = np.cumsum(people) - people
        remaining[rows, cols] -= np.clip(shelter.capacity - ahead, 0.0, people)

    people_affected = float(affected.sum())
    people_unreached = float(remaining.sum())
    people_sheltered = people_affected - people_unreached
    return SimulationResult(
        people_affected=people_affected,
        people_sheltered=people_sheltered,
        people_unreached=people_unreached,
        cost=cost,
        robustness=people_sheltered / people_affected if people_affected else 1.0,
    )


def _opened_shelters(world: World, plan: Plan) -> list[Shelter]:
    return [s for shelter_id in plan.shelter_ids if (s := world.shelter(shelter_id))]


@lru_cache(maxsize=64)
def _reachable_cells(world: World, shelter: Shelter) -> tuple[np.ndarray, np.ndarray]:
    """Rows and columns of affected cells that can reach the shelter, nearest first."""
    flooded = world.hazard.flooded
    if flooded[shelter.row, shelter.col]:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)

    # A flooded cell is one step beyond its nearest reached dry neighbor.
    distance = _dry_distance(flooded, shelter.row, shelter.col, world.reach_cells)
    padded = np.pad(np.where(distance >= 0, distance, _UNREACHED), 1, constant_values=_UNREACHED)
    nearest = np.minimum.reduce(
        [padded[:-2, 1:-1], padded[2:, 1:-1], padded[1:-1, :-2], padded[1:-1, 2:]]
    )
    steps = nearest + 1
    rows, cols = np.nonzero(flooded & (world.population > 0) & (steps <= world.reach_cells))
    order = np.argsort(steps[rows, cols], kind="stable")  # ties stay in row, then column order
    return rows[order], cols[order]


def _dry_distance(flooded: np.ndarray, row: int, col: int, reach: int) -> np.ndarray:
    """4-connected steps from (row, col) through dry cells, up to `reach`; -1 if not reached."""
    rows, cols = flooded.shape
    dry = ~flooded.ravel()
    distance = np.full(rows * cols, -1, dtype=np.int32)
    frontier = np.array([row * cols + col])
    distance[frontier] = 0
    for step in range(1, reach + 1):
        r, c = np.divmod(frontier, cols)
        neighbors = np.unique(
            np.concatenate(
                [
                    frontier[r > 0] - cols,
                    frontier[r < rows - 1] + cols,
                    frontier[c > 0] - 1,
                    frontier[c < cols - 1] + 1,
                ]
            )
        )
        frontier = neighbors[dry[neighbors] & (distance[neighbors] < 0)]
        if frontier.size == 0:
            break
        distance[frontier] = step
    return distance.reshape(rows, cols)
