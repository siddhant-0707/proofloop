"""Loop seam, evidence trail and field briefing (#10)."""

from loop_worlds import (
    offline,
    open_shelter,
    plan,
    transport,
    world_from_map,
)

from proofloop.loop import ScriptedAdversary, ScriptedPlanner, run_proofloop
from proofloop.loop.evidence import RADAR_LIMITATION
from proofloop.loop.report import write_report
from proofloop.loop.schemas import Plan, Scenario

FIGURES = {
    "people_affected",
    "people_sheltered",
    "people_unreached",
    "robustness",
    "cost",
    "unfunded_actions",
    "budget",
}

# Town S around (1, 1): one flooded cell inside a FEMA zone, one outside. Two more cells
# outside zones lie beyond every town. A dry road along the top reaches them all.
SPLIT = ["A........", ".~o....oo"]
TOWN_S = {"S": (1, 1, 1)}


def _run(world, scenario, *plans, attacks=(), rounds=1, final_attack=False):
    return run_proofloop(
        world,
        scenario,
        ScriptedPlanner(list(plans)),
        ScriptedAdversary(list(attacks) or [offline("A")]),
        rounds=rounds,
        final_attack=final_attack,
    )


def test_every_figure_of_a_round_carries_sources_formula_assumptions_and_limitations():
    world = world_from_map(SPLIT, shelters={"A": (100, 100)}, communities=TOWN_S)

    transcript = _run(
        world, Scenario(budget=10_000), plan(open_shelter("A"), cost=100, sheltered=40)
    )

    evidence = transcript.rounds[0].report.evidence
    assert set(evidence) == FIGURES
    for figure in evidence.values():
        assert figure.sources and figure.formula and figure.assumptions and figure.limitations
    for name in ("people_affected", "people_sheltered", "people_unreached", "robustness"):
        assert RADAR_LIMITATION in evidence[name].limitations
    assert set(transcript.recommendation.report.evidence) == FIGURES


def test_cost_evidence_itemizes_each_paid_action():
    world = world_from_map(SPLIT, shelters={"A": (100, 100)}, communities=TOWN_S)

    transcript = _run(
        world,
        Scenario(budget=10_000),
        plan(open_shelter("A"), open_shelter("A"), transport("S", 2), cost=400, sheltered=40),
    )

    assert transcript.rounds[0].report.evidence["cost"].inputs == [
        "Open Shelter A: $100",
        "Stage 2 transport seats for Town S: $300",
        "Total: $400",
    ]


def test_budget_evidence_shows_the_cut_from_the_starting_budget():
    world = world_from_map(SPLIT, shelters={"A": (100, 100)}, communities=TOWN_S)
    opened = Plan.model_validate(plan(open_shelter("A"), cost=100, sheltered=40))

    report = write_report(world, Scenario(budget=8_000), opened, Scenario(budget=10_000))

    assert report.evidence["budget"].inputs == [
        "Starting budget $10,000",
        "After cuts $8,000 (20% less)",
    ]


def test_briefing_splits_the_recommended_plan_by_neighborhood():
    world = world_from_map(SPLIT, shelters={"A": (100, 100)}, communities=TOWN_S)

    transcript = _run(
        world, Scenario(budget=10_000), plan(open_shelter("A"), cost=100, sheltered=40)
    )

    recommendation = transcript.recommendation
    town, rest = recommendation.report.briefing.neighborhoods
    assert (town.name, town.people_affected) == ("Town S", 20)
    assert (rest.community_id, rest.people_affected) == (None, 20)
    assert town.people_affected + rest.people_affected == recommendation.result.people_affected
    assert town.people_sheltered + rest.people_sheltered == recommendation.result.people_sheltered
    assert [(s.name, s.people) for s in town.shelters] == [("Shelter A", 20)]
    assert "Direct residents to Shelter A (about 20)." in town.steps
    assert RADAR_LIMITATION in recommendation.report.briefing.limitations


def test_briefing_shows_transport_carrying_a_town_whose_road_is_closed():
    world = world_from_map(
        ["A.~~~"], pop=10, shelters={"A": (100, 100)}, communities={"S": (0, 3, 1)}
    )

    transcript = _run(
        world,
        Scenario(budget=10_000, closed_communities=frozenset({"S"})),
        plan(open_shelter("A"), transport("S", 30), cost=4_600, sheltered=30),
    )

    (town,) = transcript.recommendation.report.briefing.neighborhoods
    assert (town.transport_seats, town.road_closed) == (30, True)
    assert [(s.people, s.carried) for s in town.shelters] == [(30, 30)]
    assert "transport is their way out." in " ".join(town.steps)
    assert "Everyone affected here can reach a shelter." in town.steps
