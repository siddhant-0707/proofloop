"""Independent check of a Plan: recompute every claimed figure in code and compare."""

from collections.abc import Callable

from proofloop.loop.schemas import Check, Plan, Scenario, Verdict
from proofloop.loop.simulation import simulate
from proofloop.world import World

# A claim matches when it is within this many units or this fraction of the actual value.
ABSOLUTE_TOLERANCE = 0.5
RELATIVE_TOLERANCE = 0.01


def verify(world: World, scenario: Scenario, plan: Plan) -> Verdict:
    actual = simulate(world, scenario, plan)
    checks = [
        _claim("cost", plan.claims.cost, actual.cost, _money),
        _claim("people_sheltered", plan.claims.people_sheltered, actual.people_sheltered, _people),
        _budget(actual.cost, scenario.budget),
        _capacity(world, scenario, plan),
        _shelters_available(world, scenario, plan),
    ]
    return Verdict(passed=all(c.passed for c in checks), checks=checks)


def _claim(name: str, claimed: float, actual: float, fmt: Callable[[float], str]) -> Check:
    tolerance = max(ABSOLUTE_TOLERANCE, RELATIVE_TOLERANCE * abs(actual))
    passed = abs(claimed - actual) <= tolerance
    reason = "" if passed else f"claimed {fmt(claimed)}, recomputed {fmt(actual)}"
    return Check(name=name, passed=passed, claimed=claimed, actual=actual, reason=reason)


def _budget(cost: float, budget: float) -> Check:
    passed = cost <= budget
    reason = "" if passed else f"costs {_money(cost)}, budget is {_money(budget)}"
    return Check(name="budget", passed=passed, claimed=cost, actual=budget, reason=reason)


def _capacity(world: World, scenario: Scenario, plan: Plan) -> Check:
    capacity = sum(
        shelter.capacity
        for shelter_id in plan.shelter_ids
        if (shelter := world.shelter(shelter_id)) and shelter_id not in scenario.offline_shelters
    )
    claimed = plan.claims.people_sheltered
    passed = claimed <= capacity
    reason = (
        ""
        if passed
        else f"claims {_people(claimed)} people, open shelters hold {_people(capacity)}"
    )
    return Check(name="capacity", passed=passed, claimed=claimed, actual=capacity, reason=reason)


def _shelters_available(world: World, scenario: Scenario, plan: Plan) -> Check:
    problems = []
    for shelter_id in plan.shelter_ids:
        if world.shelter(shelter_id) is None:
            problems.append(f"unknown shelter {shelter_id}")
        elif shelter_id in scenario.offline_shelters:
            problems.append(f"shelter {shelter_id} is offline")
    return Check(name="shelters_available", passed=not problems, reason="; ".join(problems))


def _money(amount: float) -> str:
    return f"${amount:,.0f}"


def _people(count: float) -> str:
    """Whole numbers stay whole; fractional people (Census shares) show one decimal."""
    return f"{count:,.0f}" if float(count).is_integer() else f"{count:,.1f}"
