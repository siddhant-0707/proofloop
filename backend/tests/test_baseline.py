"""The code-built baseline plan, its hedges against the failures the Adversary found, and
the backup plan for each stress case."""

from loop_worlds import offline, road_closed, world_from_map

from proofloop.loop import simulate, verify
from proofloop.loop.baseline import baseline_plan, full_cover_cost, with_backup
from proofloop.loop.schemas import ATTACK, Plan, Scenario, StressCase
from proofloop.loop.stress import apply_attack

# 30 affected people above three shelters that each reach all of them.
ROW = ["~~~", "ABC"]


def _types(plan) -> list[str]:
    return [a.type for a in plan.actions]


def test_shelters_everyone_before_surviving_an_outage():
    # A alone takes all 30; B and C together take 28 but keep 14 if one goes offline.
    world = world_from_map(ROW, shelters={"A": (30, 100), "B": (14, 60), "C": (14, 60)})

    plan = baseline_plan(world, Scenario(budget=120))

    assert plan.shelter_ids == ["A"]
    assert plan.claims.people_sheltered == 30


def test_among_plans_that_shelter_everyone_picks_the_one_that_best_survives_an_outage():
    world = world_from_map(ROW, shelters={"A": (30, 100), "B": (30, 100), "C": (30, 300)})

    plan = baseline_plan(world, Scenario(budget=200))

    assert plan.shelter_ids == ["A", "B"]


def test_stages_transport_for_a_town_whose_road_closed():
    # Town S (cols 2-4) can walk to A; once its road closes only transport reaches it.
    world = world_from_map(
        ["A.~~~"], pop=10, shelters={"A": (100, 100)}, communities={"S": (0, 3, 1)}
    )
    scenario = Scenario(budget=10_000)

    plan = baseline_plan(world, scenario, [ATTACK.validate_python(road_closed("S"))])

    assert _types(plan) == ["open_shelter", "stage_transport"]
    assert verify(world, scenario, plan).passed


def test_leaves_out_a_hedge_the_budget_cannot_pay_for():
    world = world_from_map(
        ["A.~~~"], pop=10, shelters={"A": (100, 100)}, communities={"S": (0, 3, 1)}
    )

    plan = baseline_plan(world, Scenario(budget=200), [ATTACK.validate_python(road_closed("S"))])

    assert _types(plan) == ["open_shelter"]


def test_a_backup_plan_opens_another_shelter_when_the_planned_one_goes_offline():
    world = world_from_map(ROW, shelters={"A": (30, 100), "B": (30, 100), "C": (30, 300)})
    base = Scenario(budget=150)
    plan = baseline_plan(world, base)
    attack = ATTACK.validate_python(offline("A"))
    case = StressCase(attacks=[attack], result=simulate(world, apply_attack(base, attack), plan))

    backed = with_backup(world, base, case)

    assert case.result.people_sheltered == 0
    assert backed.backup is not None
    assert Plan(actions=backed.backup.actions, claims=plan.claims).shelter_ids == ["B"]
    assert backed.backup.result.people_sheltered == 30


def test_no_backup_when_nothing_shelters_more():
    world = world_from_map(ROW, shelters={"A": (30, 100)})
    base = Scenario(budget=150)
    plan = baseline_plan(world, base)
    attack = ATTACK.validate_python(offline("A"))
    case = StressCase(attacks=[attack], result=simulate(world, apply_attack(base, attack), plan))

    assert with_backup(world, base, case).backup is None


def test_full_cover_cost_is_the_cheapest_set_of_shelters_that_takes_everyone():
    world = world_from_map(ROW, shelters={"A": (20, 100), "B": (10, 30), "C": (30, 500)})

    assert full_cover_cost(world, Scenario(budget=50)) == 130


def test_full_cover_cost_is_none_when_no_set_of_shelters_takes_everyone():
    world = world_from_map(ROW, shelters={"A": (10, 100)})

    assert full_cover_cost(world, Scenario(budget=50)) is None
