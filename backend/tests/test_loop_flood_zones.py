"""Loop seam, flooded outside the FEMA flood zone (#8): the unwarned attack and outreach."""

from loop_worlds import offline, open_shelter, outreach, plan, unwarned, world_from_map

from proofloop.loop import ScriptedAdversary, ScriptedPlanner, run_proofloop
from proofloop.loop.schemas import Scenario


def test_reports_people_flooded_outside_fema_zones_who_are_still_unreached():
    # A (capacity 10) reaches the zone cell first; the two cells outside zones stay unreached.
    world = world_from_map(["A~oo"], pop=10, shelters={"A": (10, 100)}, reach_cells=3)

    transcript = run_proofloop(
        world,
        Scenario(budget=1_000),
        ScriptedPlanner([plan(open_shelter("A"), cost=100, sheltered=10)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    result = transcript.rounds[0].result
    assert (result.people_unreached, result.people_unreached_outside_zones) == (20, 20)


# Town S around (1, 3): one flooded cell inside a FEMA zone, two outside. A dry road along
# the top lets shelter A reach all three.
TOWN = ["A.....", ".~o.o."]
TOWN_S = {"S": (1, 3, 2)}


def test_once_unwarned_people_outside_zones_stay_home_from_the_next_round():
    world = world_from_map(TOWN, pop=10, shelters={"A": (100, 100)}, communities=TOWN_S)

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000),
        ScriptedPlanner([plan(open_shelter("A"), cost=100, sheltered=30)]),
        ScriptedAdversary([unwarned()]),
        rounds=2,
    )

    first, second = transcript.rounds
    assert first.result.people_sheltered == 30
    assert second.scenario.unwarned_outside_zones
    assert second.result.people_sheltered == 10
    assert second.result.people_unreached_outside_zones == 20  # exactly the two cells outside


def test_outreach_brings_unwarned_people_in_its_community_to_shelter():
    world = world_from_map(TOWN, pop=10, shelters={"A": (100, 100)}, communities=TOWN_S)

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000, unwarned_outside_zones=True),
        ScriptedPlanner([plan(open_shelter("A"), outreach("S"), cost=5_100, sheltered=30)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    result = transcript.rounds[0].result
    assert (result.people_sheltered, result.people_unreached_outside_zones) == (30, 0)
    assert result.cost == 5_100
    assert transcript.rounds[0].verdict.passed


def test_outreach_costs_money_but_changes_nothing_before_the_attack():
    world = world_from_map(TOWN, pop=10, shelters={"A": (100, 100)}, communities=TOWN_S)

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000),
        ScriptedPlanner([plan(open_shelter("A"), outreach("S"), cost=5_100, sheltered=30)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    assert transcript.rounds[0].result.people_sheltered == 30


def test_outreach_to_an_unknown_community_fails_verification():
    world = world_from_map(TOWN, pop=10, shelters={"A": (100, 100)}, communities=TOWN_S)

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000),
        ScriptedPlanner([plan(open_shelter("A"), outreach("Z"), cost=5_100, sheltered=30)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    checks = {c.name: c.reason for c in transcript.rounds[0].verdict.checks if not c.passed}
    assert checks == {"places_available": "unknown community Z"}
