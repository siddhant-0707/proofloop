"""A hand-built World and rule-based agents for running the Loop without a model.

The World is a fictional county on an abstract grid: two flooded neighbourhoods
and six shelters. Names, capacities and costs are made up and must not be read
as real facilities.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from proofloop.loop.baseline import baseline_plan
from proofloop.loop.schemas import Plan, Round, Scenario, SimulationResult
from proofloop.loop.simulation import simulate
from proofloop.loop.stress import apply_attack, single_failures
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
    """Proposes the baseline plan, hedged against every failure the Adversary has found.

    Claims are honest except in the second round, where it overstates people sheltered
    so the Verifier has something to catch.
    """

    def propose(self, world: World, scenario: Scenario, history: Sequence[Round]) -> dict:
        plan = baseline_plan(world, scenario, [r.attack for r in history if r.attack])
        if len(history) == 1:
            claims = plan.claims.model_copy(
                update={"people_sheltered": plan.claims.people_sheltered * 1.25}
            )
            plan = plan.model_copy(
                update={"claims": claims, "rationale": plan.rationale + " (overstated on purpose)"}
            )
        return plan.model_dump()


class DemoAdversary:
    """Picks the single failure that leaves the plan sheltering the fewest people."""

    def attack(
        self, world: World, scenario: Scenario, plan: Plan | None, result: SimulationResult | None
    ) -> dict:
        if plan is None:
            target = next(s.id for s in world.shelters if s.id not in scenario.offline_shelters)
            return {"type": "shelter_offline", "shelter_id": target}
        failures = single_failures(world, scenario, plan)
        worst = min(
            failures,
            key=lambda a: simulate(world, apply_attack(scenario, a), plan).people_sheltered,
        )
        return worst.model_dump()
