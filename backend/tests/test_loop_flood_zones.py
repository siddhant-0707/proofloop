"""Loop seam, FEMA flood zones: map context only, so people outside them count the same."""

from loop_worlds import offline, open_shelter, plan, road_closed, world_from_map

from proofloop.loop import ScriptedAdversary, ScriptedPlanner, run_proofloop
from proofloop.loop.schemas import Scenario

# Town S around (1, 3): one flooded cell inside a FEMA zone, two outside. A dry road along
# the top lets shelter A reach all three.
TOWN = ["A.....", ".~o.o."]
TOWN_S = {"S": (1, 3, 2)}


def test_people_outside_fema_zones_are_affected_and_sheltered_like_everyone_else():
    world = world_from_map(TOWN, pop=10, shelters={"A": (100, 100)}, communities=TOWN_S)

    transcript = run_proofloop(
        world,
        Scenario(budget=10_000),
        ScriptedPlanner([plan(open_shelter("A"), cost=100, sheltered=30)]),
        ScriptedAdversary([road_closed("S")]),
        rounds=1,
    )

    result = transcript.rounds[0].result
    assert (result.people_affected, result.people_sheltered) == (30, 30)


def test_an_attack_that_changes_nothing_is_rejected():
    world = world_from_map(TOWN, pop=10, shelters={"A": (100, 100)}, communities=TOWN_S)
    already = Scenario(
        budget=10_000,
        offline_shelters=frozenset({"A"}),
        closed_communities=frozenset({"S"}),
    )

    for repeat, reason in (
        (offline("A"), "shelter A is already offline"),
        (road_closed("S"), "the road into S is already closed"),
    ):
        transcript = run_proofloop(
            world,
            already,
            ScriptedPlanner([plan(open_shelter("A"), cost=100, sheltered=0)]),
            ScriptedAdversary([repeat]),
            rounds=2,
        )
        first = transcript.rounds[0]
        assert first.attack is None
        assert reason in first.adversary_error
