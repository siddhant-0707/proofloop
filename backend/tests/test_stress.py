"""Single-town scope and the every-case stress test."""

from loop_worlds import open_shelter, plan, road_closed, world_from_map

from proofloop.loop import ScriptedAdversary, ScriptedPlanner, run_proofloop
from proofloop.loop.schemas import Scenario

# Town S around (1, 1) holds two flooded cells (one outside a FEMA zone); two more cells
# outside zones lie beyond every town. Town T around (1, 7) holds those two.
SPLIT = ["A...B....", ".~o....oo"]
TOWNS = {"S": (1, 1, 1), "T": (1, 7, 1)}


def _world():
    return world_from_map(SPLIT, shelters={"A": (100, 100), "B": (100, 100)}, communities=TOWNS)


def _run(scenario, attacks, rounds=1):
    return run_proofloop(
        _world(),
        scenario,
        ScriptedPlanner([plan(open_shelter("A"), cost=100, sheltered=20)]),
        ScriptedAdversary(attacks),
        rounds=rounds,
    )


def test_a_single_town_plan_counts_only_that_towns_people():
    transcript = _run(Scenario(budget=1_000, scope="S"), [road_closed("S")])

    result = transcript.rounds[0].result
    assert (result.people_affected, result.people_sheltered) == (20, 20)
    assert transcript.rounds[0].verdict.passed
    assert [n.name for n in transcript.recommendation.report.briefing.neighborhoods] == ["Town S"]


def test_closing_a_road_outside_the_scope_is_rejected():
    transcript = _run(Scenario(budget=1_000, scope="S"), [road_closed("T")])

    assert transcript.rounds[0].attack is None
    assert "outside the plan's scope" in transcript.rounds[0].adversary_error


def test_the_stress_test_tries_every_attack_alone_and_in_pairs_worst_first():
    # Only one shelter fits the budget, so the plan opening A is also the code's choice.
    transcript = _run(Scenario(budget=150, scope="S"), [road_closed("S")])

    cases = transcript.recommendation.stress.cases
    singles = {
        tuple(sorted(a.model_dump(exclude={"rationale"}).items()))
        for c in cases
        if len(c.attacks) == 1
        for a in c.attacks
    }
    assert singles == {
        (("shelter_id", "A"), ("type", "shelter_offline")),
        (("community_id", "S"), ("type", "road_closed")),
        (("percent", 10.0), ("type", "budget_cut")),
        (("percent", 25.0), ("type", "budget_cut")),
        (("percent", 50.0), ("type", "budget_cut")),
    }
    # 5 singles, 10 pairs less the 3 pairs of two budget cuts.
    assert len(cases) == 5 + 10 - 3
    assert [c.result.robustness for c in cases] == sorted(c.result.robustness for c in cases)
    assert cases[0].result.people_sheltered == 0
    assert cases[-1].result.robustness == 1.0


def test_each_failure_the_plan_cannot_ride_out_gets_a_backup_plan():
    transcript = _run(Scenario(budget=150, scope="S"), [road_closed("S")])

    cases = transcript.recommendation.stress.cases
    a_offline = next(
        c
        for c in cases
        if [a.model_dump(exclude={"rationale"}) for a in c.attacks]
        == [{"type": "shelter_offline", "shelter_id": "A"}]
    )
    assert a_offline.result.people_sheltered == 0
    assert a_offline.backup is not None
    assert [a.model_dump() for a in a_offline.backup.actions] == [
        {"type": "open_shelter", "shelter_id": "B"}
    ]
    assert a_offline.backup.result.people_sheltered == 20
    # A plan that already shelters everyone needs no backup.
    assert all(c.backup is None for c in cases if c.result.robustness == 1.0)


def test_a_budget_too_small_to_shelter_everyone_reports_what_would():
    transcript = run_proofloop(
        _world(),
        Scenario(budget=50, scope="S"),
        ScriptedPlanner([plan(cost=0, sheltered=0)]),
        ScriptedAdversary([road_closed("S")]),
        rounds=1,
    )

    rec = transcript.recommendation
    assert rec.result.people_sheltered == 0
    assert rec.full_cover_cost == 100
    assert (
        _run(Scenario(budget=1_000, scope="S"), [road_closed("S")]).recommendation.full_cover_cost
        is None
    )


def _totals_match(briefing, result) -> None:
    assert briefing is not None
    hoods = briefing.neighborhoods
    assert sum(n.people_affected for n in hoods) == result.people_affected
    assert sum(n.people_sheltered for n in hoods) == result.people_sheltered
    assert sum(n.people_unreached for n in hoods) == result.people_unreached


def _sent_to(briefing) -> set[str]:
    return {s.shelter_id for n in briefing.neighborhoods for s in n.shelters}


def test_each_stress_case_says_where_people_go_under_its_failures():
    rec = _run(Scenario(budget=150, scope="S"), [road_closed("S")]).recommendation

    for case in [*rec.stress.cases, rec.combined]:
        _totals_match(case.briefing, case.result)
        offline = {a.shelter_id for a in case.attacks if a.type == "shelter_offline"}
        assert not _sent_to(case.briefing) & offline
        closed = {a.community_id for a in case.attacks if a.type == "road_closed"}
        assert {n.community_id for n in case.briefing.neighborhoods if n.road_closed} == closed


def test_each_backup_plan_says_where_people_go_under_the_same_failures():
    rec = _run(Scenario(budget=150, scope="S"), [road_closed("S")]).recommendation

    backed = [c for c in rec.stress.cases if c.backup]
    assert backed
    for case in backed:
        _totals_match(case.backup.briefing, case.backup.result)
        opened = {a.shelter_id for a in case.backup.actions if a.type == "open_shelter"}
        assert _sent_to(case.backup.briefing) <= opened
