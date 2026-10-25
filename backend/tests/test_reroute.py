"""Loop seam: where people go once the Adversary's attack hits (#26)."""

from loop_worlds import offline, open_plan, road_closed, world_from_map

from proofloop.loop import ScriptedAdversary, ScriptedPlanner, run_proofloop
from proofloop.loop.schemas import Round, Scenario

# Town S holds the four flooded cells between shelters A and B; a dry road runs above them.
TWO_SHELTERS = ["A......B", "..~~~~.."]
TOWN_S = {"S": (1, 4, 2)}


def _round(world, plan, attack, *, final_attack=True) -> Round:
    transcript = run_proofloop(
        world,
        Scenario(budget=10_000),
        ScriptedPlanner([plan]),
        ScriptedAdversary([attack]),
        rounds=1,
        final_attack=final_attack,
    )
    return transcript.rounds[0]


def _totals_match(round: Round) -> None:
    briefing, attacked = round.attacked_briefing, round.attacked
    assert briefing is not None and attacked is not None
    neighborhoods = briefing.neighborhoods
    assert sum(n.people_affected for n in neighborhoods) == attacked.people_affected
    assert sum(n.people_sheltered for n in neighborhoods) == attacked.people_sheltered
    assert sum(n.people_unreached for n in neighborhoods) == attacked.people_unreached


def test_people_heading_to_a_shelter_that_goes_offline_reroute_to_the_one_still_open():
    world = world_from_map(
        TWO_SHELTERS, pop=10, shelters={"A": (20, 100), "B": (100, 100)}, communities=TOWN_S
    )

    round = _round(world, open_plan("A", "B", cost=200, sheltered=40), offline("A"))

    assert round.report is not None
    planned = {s.shelter_id for n in round.report.briefing.neighborhoods for s in n.shelters}
    assert planned == {"A", "B"}
    assert round.attacked_briefing is not None
    (town,) = round.attacked_briefing.neighborhoods
    assert [(s.shelter_id, s.people) for s in town.shelters] == [("B", 40)]
    _totals_match(round)


def test_a_town_whose_road_closes_is_marked_cut_off_with_its_people_unreached():
    world = world_from_map(
        ["A.~~~"], pop=10, shelters={"A": (100, 100)}, communities={"S": (0, 3, 1)}
    )

    round = _round(world, open_plan("A", cost=100, sheltered=30), road_closed("S"))

    assert round.attacked_briefing is not None
    (town,) = round.attacked_briefing.neighborhoods
    assert town.road_closed
    assert town.shelters == []
    assert town.people_unreached == town.people_affected == 30
    _totals_match(round)


def test_a_round_without_an_attack_has_no_rerouting():
    world = world_from_map(TWO_SHELTERS, pop=10, shelters={"A": (100, 100), "B": (100, 100)})

    round = _round(
        world, open_plan("A", "B", cost=200, sheltered=40), offline("A"), final_attack=False
    )

    assert round.attack is None
    assert round.attacked_briefing is None
