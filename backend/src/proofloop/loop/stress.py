"""Every-case stress check of a plan.

Users choose only the scope and the budget. Which shelters fail, which roads close
and how deep the budget is cut is for the stress test to find: besides the
Adversary's attacks, code scores the recommended plan under every single attack and
every pair, on top of the base scenario. Single failures are small trouble a plan
should ride out; pairs are major trouble, reported but never held against a plan.
"""

from collections.abc import Sequence
from itertools import combinations

from proofloop.loop.briefing import brief
from proofloop.loop.schemas import (
    Attack,
    BudgetCut,
    Plan,
    RoadClosed,
    Scenario,
    ShelterOffline,
    StressCase,
    StressTest,
)
from proofloop.loop.simulation import affected_people, simulate, trace
from proofloop.world import World

BUDGET_CUTS = (10.0, 25.0, 50.0)


def stress_test(world: World, base: Scenario, plan: Plan) -> StressTest:
    cases = [stress_case(world, base, plan, attacks) for attacks in stress_cases(world, base, plan)]
    cases.sort(key=lambda c: (c.result.robustness, len(c.attacks)))
    return StressTest(cases=cases)


def stress_case(world: World, base: Scenario, plan: Plan, attacks: list[Attack]) -> StressCase:
    """The plan under `attacks`: its score, and where people go."""
    hit = apply_all(base, attacks)
    traced = trace(world, hit, plan)
    return StressCase(attacks=attacks, result=traced.result, briefing=brief(world, hit, traced))


def typical(world: World, base: Scenario, plan: Plan) -> float:
    """Average share sheltered over every single failure: how much small trouble hurts."""
    shares = [
        simulate(world, apply_attack(base, attack), plan).robustness
        for attack in single_failures(world, base, plan)
    ]
    return sum(shares) / len(shares)


def stress_cases(world: World, base: Scenario, plan: Plan) -> list[list[Attack]]:
    """Each attack that could hurt the plan, alone and in pairs (never two budget cuts)."""
    singles = single_failures(world, base, plan)
    pairs = [
        [a, b]
        for a, b in combinations(singles, 2)
        if not (isinstance(a, BudgetCut) and isinstance(b, BudgetCut))
    ]
    return [[a] for a in singles] + pairs


def single_failures(world: World, base: Scenario, plan: Plan) -> list[Attack]:
    """Each shelter the plan opens going offline, each affected town's road closing and
    each budget cut."""
    affected = affected_people(world, base)
    singles: list[Attack] = [
        ShelterOffline(shelter_id=s)
        for s in plan.shelter_ids
        if world.shelter(s) and s not in base.offline_shelters
    ]
    singles += [
        RoadClosed(community_id=c.id)
        for c in world.communities
        if c.id not in base.closed_communities and affected[c.mask(world.grid.shape)].sum() > 0
    ]
    singles += [BudgetCut(percent=p) for p in BUDGET_CUTS]
    return singles


def apply_attack(scenario: Scenario, attack: Attack) -> Scenario:
    if isinstance(attack, ShelterOffline):
        return scenario.with_offline(attack.shelter_id)
    if isinstance(attack, RoadClosed):
        return scenario.with_closed(attack.community_id)
    assert isinstance(attack, BudgetCut)
    return scenario.with_budget_cut(attack.percent)


def unique_attacks(attacks: Sequence[Attack]) -> list[Attack]:
    """In first-seen order; attacks differing only in rationale are the same."""
    seen: dict[str, Attack] = {}
    for attack in attacks:
        seen.setdefault(attack.model_dump_json(exclude={"rationale"}), attack)
    return list(seen.values())


def apply_all(scenario: Scenario, attacks: list[Attack]) -> Scenario:
    for attack in attacks:
        scenario = apply_attack(scenario, attack)
    return scenario
