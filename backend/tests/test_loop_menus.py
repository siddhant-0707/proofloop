"""Loop seam, full action and attack menus (#7): transport, reserve, road closed, budget cut."""

from dataclasses import replace

from loop_worlds import (
    budget_cut,
    offline,
    open_shelter,
    plan,
    reserve,
    road_closed,
    transport,
    world_from_map,
)

from proofloop.loop import ScriptedAdversary, ScriptedPlanner, run_proofloop
from proofloop.loop.schemas import Scenario

# Shelter A is too far for the coastal town S (cols 6-8) to walk to.
CUT_OFF = ["A.....~~~"]
TOWN = {"S": (0, 7, 1)}


def test_staged_transport_carries_cut_off_people_to_an_open_shelter():
    world = world_from_map(
        CUT_OFF, pop=10, shelters={"A": (100, 100)}, communities=TOWN, reach_cells=2
    )

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000),
        ScriptedPlanner([plan(open_shelter("A"), transport("S", 20), cost=3_100, sheltered=20)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    result = transcript.rounds[0].result
    assert (result.people_affected, result.people_sheltered) == (30, 20)
    assert result.cost == 3_100  # $100 shelter + 20 seats x $150
    assert transcript.rounds[0].verdict.passed


def test_transport_only_fills_beds_left_in_open_shelters():
    world = world_from_map(
        CUT_OFF, pop=10, shelters={"A": (15, 100)}, communities=TOWN, reach_cells=2
    )

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000),
        ScriptedPlanner([plan(open_shelter("A"), transport("S", 30), cost=4_600, sheltered=15)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    assert transcript.rounds[0].result.people_sheltered == 15  # 30 seats, 15 beds


def test_a_closed_road_stops_a_town_walking_to_shelter():
    # Town S (cols 2-4) can walk to A; once its road closes it cannot.
    world = world_from_map(
        ["A.~~~"], pop=10, shelters={"A": (100, 100)}, communities={"S": (0, 3, 1)}
    )

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000),
        ScriptedPlanner([plan(open_shelter("A"), cost=100, sheltered=10)]),
        ScriptedAdversary([road_closed("S")]),
        rounds=1,
    )

    first = transcript.rounds[0]
    assert first.result.people_sheltered == 10
    assert first.attacked.people_sheltered == 0


def test_transport_reaches_a_town_whose_road_is_closed():
    world = world_from_map(
        ["A.~~~"], pop=10, shelters={"A": (100, 100)}, communities={"S": (0, 3, 1)}
    )

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000, closed_communities=frozenset({"S"})),
        ScriptedPlanner([plan(open_shelter("A"), transport("S", 30), cost=4_600, sheltered=30)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    assert transcript.rounds[0].result.people_sheltered == 30


def test_a_budget_cut_is_a_test_and_leaves_the_next_rounds_budget_alone():
    world = world_from_map(["A.~"], pop=10, shelters={"A": (10, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1_000),
        ScriptedPlanner([plan(open_shelter("A"), cost=100, sheltered=10)]),
        ScriptedAdversary([budget_cut(25)]),
        rounds=2,
    )

    assert transcript.rounds[1].scenario.budget == 1_000


def test_after_a_cut_actions_beyond_the_budget_lose_funding_in_plan_order():
    # Budget 400 -> 300 after a 25% cut: A ($200) stays funded, B ($200) loses its money.
    world = world_from_map(["A.~.B"], pop=10, shelters={"A": (5, 200), "B": (5, 200)})
    both = plan(open_shelter("A"), open_shelter("B"), cost=400, sheltered=10)

    transcript = run_proofloop(
        world,
        Scenario(budget=400),
        ScriptedPlanner([both]),
        ScriptedAdversary([budget_cut(25)]),
        rounds=1,
    )

    attacked = transcript.rounds[0].attacked
    assert (attacked.people_sheltered, attacked.unfunded_actions) == (5, 1)


def test_a_contingency_reserve_keeps_a_plan_funded_through_a_budget_cut():
    # $3,000 budget, cut 30% to $2,100. Shelter C is out of reach, so money on it is wasted.
    world = world_from_map(["A.~.......C"], pop=10, shelters={"A": (10, 2_000), "C": (10, 1_000)})
    world = replace(world, reach_cells=2)
    held_back = plan(open_shelter("A"), reserve(1_000), cost=3_000, sheltered=10)
    wasted = plan(open_shelter("C"), open_shelter("A"), cost=3_000, sheltered=10)

    sheltered = {}
    for name, chosen in (("reserve", held_back), ("wasted", wasted)):
        transcript = run_proofloop(
            world,
            Scenario(budget=3_000),
            ScriptedPlanner([chosen]),
            ScriptedAdversary([budget_cut(30)]),
            rounds=1,
        )
        sheltered[name] = transcript.rounds[0].attacked.people_sheltered

    # The reserve absorbs the cut; the wasted $1,000 pushes A past the new budget.
    assert sheltered == {"reserve": 10, "wasted": 0}


def test_unknown_communities_are_rejected_in_plans_and_attacks():
    world = world_from_map(["A.~"], pop=10, shelters={"A": (10, 100)}, communities={"S": (0, 2, 1)})

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000),
        ScriptedPlanner([plan(open_shelter("A"), transport("Z", 5), cost=850, sheltered=10)]),
        ScriptedAdversary([road_closed("Z")]),
        rounds=2,
    )

    availability = [c for c in transcript.rounds[0].verdict.checks if c.name == "places_available"]
    assert availability[0].reason == "unknown community Z"
    assert "unknown community Z" in transcript.rounds[0].adversary_error


def test_people_in_a_closed_town_can_still_reach_a_shelter_inside_it():
    # Town S (cols 2-6) holds shelter B; its closed road only cuts it off from A outside.
    # Without the closure A would reach col 2 (10 people); B reaches cols 3 and 5 (20).
    world = world_from_map(
        ["A.~~B~~"],
        pop=10,
        shelters={"A": (100, 100), "B": (100, 100)},
        communities={"S": (0, 4, 2)},
    )
    closed = Scenario(budget=10_000, closed_communities=frozenset({"S"}))

    sheltered = {}
    for name in ("A", "B"):
        transcript = run_proofloop(
            world,
            closed,
            ScriptedPlanner([plan(open_shelter(name), cost=100, sheltered=0)]),
            ScriptedAdversary([offline(name)]),
            rounds=1,
        )
        sheltered[name] = transcript.rounds[0].result.people_sheltered

    assert sheltered == {"A": 0, "B": 20}


def test_funding_stops_at_the_first_action_the_budget_cannot_cover():
    # Budget $250: A ($200) is funded; B ($100) no longer fits, and C ($20) after it gets
    # nothing either, even though it alone would fit. Actions lose money last first.
    world = world_from_map(
        ["A.~.B.~.C.~"], pop=10, shelters={"A": (10, 200), "B": (10, 100), "C": (10, 20)}
    )
    ordered = plan(open_shelter("A"), open_shelter("B"), open_shelter("C"), cost=320, sheltered=30)

    transcript = run_proofloop(
        world,
        Scenario(budget=250),
        ScriptedPlanner([ordered]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    result = transcript.rounds[0].result
    assert (result.people_sheltered, result.unfunded_actions) == (10, 2)


def test_a_shelter_opened_twice_is_paid_for_once():
    world = world_from_map(["A.~"], pop=10, shelters={"A": (10, 100)})
    twice = plan(open_shelter("A"), open_shelter("A"), cost=100, sheltered=10)

    transcript = run_proofloop(
        world,
        Scenario(budget=1_000),
        ScriptedPlanner([twice]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    assert transcript.rounds[0].result.cost == 100
    assert transcript.rounds[0].verdict.passed


def test_a_budget_cut_below_ten_percent_is_rejected():
    world = world_from_map(["A.~"], pop=10, shelters={"A": (10, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1_000),
        ScriptedPlanner([plan(open_shelter("A"), cost=100, sheltered=10)]),
        ScriptedAdversary([budget_cut(5)]),
        rounds=2,
    )

    assert transcript.rounds[0].attack is None
    assert "percent" in transcript.rounds[0].adversary_error
