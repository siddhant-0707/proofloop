"""Deterministic scoring of a Plan against a World under a Scenario. No randomness, no LLM.

People in flooded cells are affected. An affected cell can reach an open shelter
when a 4-connected path from it to the shelter, at most `world.reach_cells` steps
long, crosses only dry cells after leaving the starting cell. Each shelter fills
its capacity with the nearest reachable people first; shelters are filled in
plan order and ties break by row, then column.

People in a community whose road is closed cannot reach a shelter outside it on
their own; a shelter inside the community stays reachable for them.
Staged transport then carries a community's remaining people, nearest to its
center first, into open shelters that still have room, closed road or not.

Actions are funded in plan order while their running cost fits the budget; a
contingency reserve is money held back, so it needs no funding. A plan that the
budget (after any cut) cannot fully fund loses its last actions.
"""

from functools import lru_cache

import numpy as np

from proofloop.loop.schemas import (
    Action,
    AllocateBudget,
    OpenShelter,
    Plan,
    Scenario,
    SimulationResult,
    StageTransport,
)
from proofloop.world import Shelter, World

_UNREACHED = np.iinfo(np.int32).max // 2


def simulate(world: World, scenario: Scenario, plan: Plan) -> SimulationResult:
    affected = np.where(world.hazard.flooded, world.population, 0.0)
    remaining = affected.copy()
    funded, unfunded = _funded_actions(world, scenario, plan)

    room: dict[str, float] = {}  # spare capacity of each open shelter, in plan order
    for action in funded:
        if isinstance(action, OpenShelter):
            shelter = world.shelter(action.shelter_id)
            if shelter is None or shelter.id in scenario.offline_shelters:
                continue
            rows, cols = _reachable_cells(world, shelter)
            keep = ~_cells_cut_off_from_shelter(world, scenario, shelter)[rows, cols]
            room[shelter.id] = shelter.capacity - _fill(
                remaining, rows[keep], cols[keep], shelter.capacity
            )

    for action in funded:
        if isinstance(action, StageTransport):
            _transport(world, action, remaining, room)

    people_affected = float(affected.sum())
    people_unreached = float(remaining.sum())
    people_sheltered = people_affected - people_unreached
    return SimulationResult(
        people_affected=people_affected,
        people_sheltered=people_sheltered,
        people_unreached=people_unreached,
        cost=sum(action_cost(world, a) for a in _billable(plan.actions)),
        robustness=people_sheltered / people_affected if people_affected else 1.0,
        unfunded_actions=unfunded,
    )


def action_cost(world: World, action: Action) -> float:
    if isinstance(action, OpenShelter):
        shelter = world.shelter(action.shelter_id)
        return shelter.cost if shelter else 0.0
    if isinstance(action, StageTransport):
        return action.seats * world.transport_cost_per_seat
    return action.amount


def _funded_actions(world: World, scenario: Scenario, plan: Plan) -> tuple[list[Action], int]:
    """Actions funded in plan order until the first one the budget cannot cover.

    That action and every later one lose their money (the last actions are dropped
    first). The reserve is held back, not spent, so it needs no funding.
    """
    spent = 0.0
    actions: list[Action] = [
        a for a in _billable(plan.actions) if not isinstance(a, AllocateBudget)
    ]
    for i, action in enumerate(actions):
        spent += action_cost(world, action)
        if spent > scenario.budget:
            return actions[:i], len(actions) - i
    return actions, 0


def _billable(actions: list[Action]) -> list[Action]:
    """The plan's actions with repeated shelter openings removed: a shelter is paid for once."""
    seen: set[str] = set()
    billable: list[Action] = []
    for action in actions:
        if isinstance(action, OpenShelter):
            if action.shelter_id in seen:
                continue
            seen.add(action.shelter_id)
        billable.append(action)
    return billable


def _cells_cut_off_from_shelter(world: World, scenario: Scenario, shelter: Shelter) -> np.ndarray:
    """Cells in closed communities that do not contain the shelter."""
    cut_off = np.zeros(world.grid.shape, dtype=bool)
    for community_id in scenario.closed_communities:
        community = world.community(community_id)
        if community is None:
            continue
        mask = community.mask(world.grid.shape)
        if not mask[shelter.row, shelter.col]:
            cut_off |= mask
    return cut_off


def _fill(remaining: np.ndarray, rows: np.ndarray, cols: np.ndarray, capacity: float) -> float:
    """Take up to `capacity` people from the cells in order; return how many were taken."""
    people = remaining[rows, cols]
    ahead = np.cumsum(people) - people
    taken = np.clip(capacity - ahead, 0.0, people)
    remaining[rows, cols] -= taken
    return float(taken.sum())


def _transport(
    world: World, action: StageTransport, remaining: np.ndarray, room: dict[str, float]
) -> None:
    community = world.community(action.community_id)
    if community is None:
        return
    seats = min(float(action.seats), sum(room.values()))
    rows, cols = np.nonzero(community.mask(world.grid.shape) & (remaining > 0))
    order = np.argsort((rows - community.row) ** 2 + (cols - community.col) ** 2, kind="stable")
    moved = _fill(remaining, rows[order], cols[order], seats)
    for shelter_id in room:  # the people moved take spare beds in plan order
        taken = min(room[shelter_id], moved)
        room[shelter_id] -= taken
        moved -= taken


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
