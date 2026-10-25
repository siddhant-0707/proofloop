"""Plans built by code: what the rule-based Planner proposes, the fallback when no
Planner's plan passes verification, and the backup plan for each stress case.

It opens the affordable set of shelters that shelters the most people, and among
those the set that best survives losing any one of them; then it adds transport for
each town whose road the Adversary closed, while the budget allows. A hedge is kept
only if it shelters nobody fewer as planned and more under its failure. Shelters
come first in plan order, so a budget cut drops hedges before shelters. Claims are
the simulated figures.
"""

import math
from collections.abc import Sequence
from itertools import combinations

from proofloop.loop.briefing import brief
from proofloop.loop.describe import describe_action
from proofloop.loop.schemas import (
    Action,
    Attack,
    Backup,
    Claims,
    OpenShelter,
    Plan,
    RoadClosed,
    Scenario,
    StageTransport,
    StressCase,
)
from proofloop.loop.simulation import affected_people, simulate, trace
from proofloop.loop.stress import apply_all, apply_attack, unique_attacks
from proofloop.world import World

MAX_SEATS = 5_000
# A backup must shelter at least this many more people than the plan to be worth a switch.
_MIN_GAIN = 0.5


def baseline_plan(world: World, scenario: Scenario, found: Sequence[Attack] = ()) -> Plan:
    actions: list[Action] = [OpenShelter(shelter_id=s) for s in _shelters(world, scenario)]
    hedges: list[Action] = []
    for attack in unique_attacks(found):
        for hedge in _hedges(world, scenario, attack, actions):
            if _helps(world, scenario, attack, actions, hedge):
                actions, hedges = [*actions, hedge], [*hedges, hedge]
    result = simulate(world, scenario, _plan(actions))
    opened = [
        s.name for a in actions if isinstance(a, OpenShelter) and (s := world.shelter(a.shelter_id))
    ]
    rationale = (
        f"Open {_join(opened)}: the affordable set that shelters the most people, and best "
        "survives losing one."
        if opened
        else "No shelter fits the budget."
    )
    if hedges:
        rationale += (
            " Against the failures found: "
            + _join([describe_action(h, world) for h in hedges])
            + "."
        )
    return Plan(
        # Room left for the rule-based Planner's note on its overstated round.
        rationale=rationale[:560],
        actions=actions,
        claims=Claims(cost=result.cost, people_sheltered=result.people_sheltered),
    )


def with_backup(world: World, base: Scenario, case: StressCase) -> StressCase:
    """The case with a backup plan, built for its failures, when that shelters more."""
    hit = apply_all(base, case.attacks)
    plan = baseline_plan(world, hit, case.attacks)
    traced = trace(world, hit, plan)
    if traced.result.people_sheltered < case.result.people_sheltered + _MIN_GAIN:
        return case
    backup = Backup(actions=plan.actions, result=traced.result, briefing=brief(world, hit, traced))
    return case.model_copy(update={"backup": backup})


def full_cover_cost(world: World, scenario: Scenario) -> float | None:
    """The cheapest set of open shelters that shelters everyone affected; None if no set does."""
    available = [s.id for s in world.shelters if s.id not in scenario.offline_shelters]
    affected = float(affected_people(world, scenario).sum())
    unlimited = scenario.model_copy(update={"budget": sum(s.cost for s in world.shelters)})
    costs: list[float] = []
    for size in range(1, len(available) + 1):
        for ids in combinations(available, size):
            result = simulate(world, unlimited, _plan([OpenShelter(shelter_id=s) for s in ids]))
            if result.people_sheltered >= affected - _MIN_GAIN:
                costs.append(result.cost)
    return min(costs, default=None)


def _shelters(world: World, scenario: Scenario) -> list[str]:
    """Ranked by people sheltered with every shelter up, then in the worst single outage,
    then by lower cost."""
    available = [s.id for s in world.shelters if s.id not in scenario.offline_shelters]
    best: tuple[tuple[float, float, float], list[str]] | None = None
    for size in range(1, len(available) + 1):
        for ids in combinations(available, size):
            opened = _plan([OpenShelter(shelter_id=s) for s in ids])
            result = simulate(world, scenario, opened)
            if result.cost > scenario.budget:
                continue
            worst = min(
                simulate(world, scenario.with_offline(lost), opened).people_sheltered
                for lost in ids
            )
            key = (round(result.people_sheltered, 6), round(worst, 6), -result.cost)
            if best is None or key > best[0]:
                best = (key, list(ids))
    return best[1] if best else []


def _hedges(
    world: World, scenario: Scenario, attack: Attack, actions: list[Action]
) -> list[Action]:
    if not (isinstance(attack, RoadClosed) and (town := world.community(attack.community_id))):
        return []
    spare = scenario.budget - simulate(world, scenario, _plan(actions)).cost
    affected = affected_people(world, scenario)
    needed = math.ceil(float(affected[town.mask(world.grid.shape)].sum()))
    seats = min(needed, MAX_SEATS, int(spare // world.transport_cost_per_seat))
    return [StageTransport(community_id=town.id, seats=seats)] if seats >= 1 else []


def _helps(
    world: World, scenario: Scenario, attack: Attack, actions: list[Action], hedge: Action
) -> bool:
    before, after = _plan(actions), _plan([*actions, hedge])
    planned = simulate(world, scenario, after)
    if planned.cost > scenario.budget:
        return False
    if planned.people_sheltered < simulate(world, scenario, before).people_sheltered:
        return False
    hit = apply_attack(scenario, attack)
    return (
        simulate(world, hit, after).people_sheltered > simulate(world, hit, before).people_sheltered
    )


def _plan(actions: Sequence[Action]) -> Plan:
    return Plan(actions=list(actions), claims=Claims(cost=0, people_sheltered=0))


def _join(items: list[str]) -> str:
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
