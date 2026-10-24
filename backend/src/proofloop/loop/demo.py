"""A hand-built World and rule-based agents for running the Loop without Gemini.

The World is a fictional county on an abstract grid: two flooded neighbourhoods
and six shelters. Names, capacities and costs are made up and must not be read
as real facilities.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from proofloop.loop.schemas import Plan, Round, Scenario, SimulationResult
from proofloop.loop.simulation import simulate
from proofloop.world import Grid, HazardLayer, Shelter, World

# ~ flooded (people live here), . dry, letters are shelters.
_MAP = [
    "..A.......B...",
    "..............",
    "....~~....~...",
    "...~~~~..~~~..",
    ".E.~~~~..~~~.C",
    "...~~~.....~..",
    ".....~~~.~~...",
    "..F...~~~~..D.",
    "..............",
]


@dataclass(frozen=True)
class _DemoShelter:
    name: str
    capacity: float
    cost: float


_SHELTERS = {
    "A": _DemoShelter("Demo High School", capacity=180, cost=4_000),
    "B": _DemoShelter("Demo Civic Center", capacity=120, cost=2_500),
    "C": _DemoShelter("Demo Community Center", capacity=90, cost=1_500),
    "D": _DemoShelter("Demo Fire Station", capacity=60, cost=1_000),
    "E": _DemoShelter("Demo Elementary School", capacity=100, cost=2_000),
    "F": _DemoShelter("Demo Library", capacity=80, cost=1_200),
}
_PEOPLE_PER_FLOODED_CELL = 12.0

DEMO_SCENARIO = Scenario(budget=7_000)


def demo_world() -> World:
    flooded = np.array([[ch == "~" for ch in row] for row in _MAP])
    rows, cols = flooded.shape
    return World(
        # Abstract coordinates: the demo county is not a real place.
        grid=Grid(latitude=np.linspace(0.0, -0.1, rows), longitude=np.linspace(0.0, 0.15, cols)),
        hazard=HazardLayer(flooded=flooded, confidence=flooded * 0.9, method="hand-built"),
        population=np.where(flooded, _PEOPLE_PER_FLOODED_CELL, 0.0),
        shelters=tuple(
            Shelter(
                id=ch,
                name=_SHELTERS[ch].name,
                row=r,
                col=c,
                capacity=_SHELTERS[ch].capacity,
                cost=_SHELTERS[ch].cost,
            )
            for r, row in enumerate(_MAP)
            for c, ch in enumerate(row)
            if ch in _SHELTERS
        ),
        reach_cells=6,
    )


class DemoPlanner:
    """Opens the affordable set of available shelters that best survives losing any one of them.

    Sets are ranked by people sheltered in the worst single-shelter outage, then
    by people sheltered with all shelters up, then by lower cost. Claims are
    honest except in the second round, where it overstates people sheltered so
    the Verifier has something to catch.
    """

    def propose(self, world: World, scenario: Scenario, history: Sequence[Round]) -> dict:
        available = [s.id for s in world.shelters if s.id not in scenario.offline_shelters]
        best: tuple[tuple[float, float, float], Plan] | None = None
        for size in range(1, len(available) + 1):
            for ids in combinations(available, size):
                result = simulate(world, scenario, _plan(list(ids), cost=0, sheltered=0))
                if result.cost > scenario.budget:
                    continue
                key = (
                    _worst_outage(world, scenario, list(ids)),
                    result.people_sheltered,
                    -result.cost,
                )
                if best is None or key > best[0]:
                    best = (key, _plan(list(ids), result.cost, result.people_sheltered))
        if best is None:
            return _plan([], cost=0, sheltered=0).model_dump()

        plan = best[1]
        if len(history) == 1:
            claims = plan.claims.model_copy(
                update={"people_sheltered": plan.claims.people_sheltered * 1.25}
            )
            plan = plan.model_copy(
                update={"claims": claims, "rationale": plan.rationale + " (overstated on purpose)"}
            )
        return plan.model_dump()


class DemoAdversary:
    """Takes offline the open shelter whose loss leaves the most people unreached."""

    def attack(
        self, world: World, scenario: Scenario, plan: Plan | None, result: SimulationResult | None
    ) -> dict:
        candidates = plan.shelter_ids if plan else [s.id for s in world.shelters]
        candidates = [c for c in candidates if c not in scenario.offline_shelters] or candidates

        def damage(shelter_id: str) -> float:
            hit = scenario.with_offline(shelter_id)
            return simulate(world, hit, plan).people_unreached if plan else 0.0

        target = max(candidates, key=damage)
        return {"type": "shelter_offline", "shelter_id": target}


def _plan(shelter_ids: list[str], cost: float, sheltered: float) -> Plan:
    names = ", ".join(shelter_ids) or "no shelters"
    return Plan.model_validate(
        {
            "actions": [{"type": "open_shelter", "shelter_id": s} for s in shelter_ids],
            "claims": {"cost": cost, "people_sheltered": sheltered},
            "rationale": f"Open {names}: the affordable set that shelters the most people.",
        }
    )


def _worst_outage(world: World, scenario: Scenario, shelter_ids: list[str]) -> float:
    """People sheltered if the most damaging single shelter in the set goes offline."""
    plan = _plan(shelter_ids, cost=0, sheltered=0)
    return min(
        simulate(world, scenario.with_offline(lost), plan).people_sheltered for lost in shelter_ids
    )
