"""Deterministic scoring of a Plan against a World under a Scenario. No randomness, no LLM.

People in flooded cells are affected. An affected cell can reach an open shelter
when a 4-connected path from it to the shelter, at most `world.reach_cells` steps
long, crosses only dry cells after leaving the starting cell. Each shelter fills
its capacity with the nearest reachable people first; shelters are filled in
plan order and ties break by row, then column.
"""

from collections import deque

import numpy as np

from proofloop.loop.schemas import Plan, Scenario, SimulationResult
from proofloop.world import Shelter, World


def simulate(world: World, scenario: Scenario, plan: Plan) -> SimulationResult:
    affected = np.where(world.hazard.flooded, world.population, 0.0)
    remaining = affected.copy()
    cost = 0.0

    for shelter in _opened_shelters(world, plan):
        cost += shelter.cost
        if shelter.id in scenario.offline_shelters:
            continue
        capacity = shelter.capacity
        for row, col in _reachable_cells(world, shelter):
            if capacity <= 0:
                break
            taken = min(capacity, remaining[row, col])
            remaining[row, col] -= taken
            capacity -= taken

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


def _reachable_cells(world: World, shelter: Shelter) -> list[tuple[int, int]]:
    """Affected cells that can reach the shelter, nearest first."""
    flooded = world.hazard.flooded
    rows, cols = flooded.shape
    if flooded[shelter.row, shelter.col]:
        return []

    # Breadth-first search over dry cells from the shelter.
    dry_distance = np.full((rows, cols), -1, dtype=np.int64)
    dry_distance[shelter.row, shelter.col] = 0
    queue = deque([(shelter.row, shelter.col)])
    while queue:
        r, c = queue.popleft()
        if dry_distance[r, c] >= world.reach_cells:
            continue
        for nr, nc in _neighbors(r, c, rows, cols):
            if dry_distance[nr, nc] < 0 and not flooded[nr, nc]:
                dry_distance[nr, nc] = dry_distance[r, c] + 1
                queue.append((nr, nc))

    # A flooded cell is one step beyond its nearest reached dry neighbor.
    reachable = []
    for r, c in zip(*np.nonzero(flooded & (world.population > 0)), strict=True):
        steps = [
            dry_distance[nr, nc] + 1
            for nr, nc in _neighbors(r, c, rows, cols)
            if dry_distance[nr, nc] >= 0
        ]
        if steps and min(steps) <= world.reach_cells:
            reachable.append((min(steps), int(r), int(c)))
    return [(r, c) for _, r, c in sorted(reachable)]


def _neighbors(r: int, c: int, rows: int, cols: int):
    for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
        if 0 <= nr < rows and 0 <= nc < cols:
            yield nr, nc
