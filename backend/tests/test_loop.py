"""Loop seam: run_proofloop(world, scenario, planner, adversary) -> Transcript.

Worlds are drawn as small maps:
    ~  flooded cell holding `pop` affected people
    .  dry, passable cell
    A-Z shelter on a dry cell
"""

from dataclasses import replace

import numpy as np

from proofloop.loop import ScriptedAdversary, ScriptedPlanner, run_proofloop
from proofloop.loop.schemas import Scenario
from proofloop.world import Grid, HazardLayer, Shelter, World


def world_from_map(rows: list[str], pop: float = 10.0, shelters=None) -> World:
    """shelters maps a letter to (capacity, cost)."""
    shelters = shelters or {}
    flooded = np.array([[ch == "~" for ch in row] for row in rows])
    n_rows, n_cols = flooded.shape
    return World(
        grid=Grid(
            latitude=np.linspace(30.0, 29.9, n_rows),
            longitude=np.linspace(-83.5, -83.4, n_cols),
        ),
        hazard=HazardLayer(
            flooded=flooded,
            confidence=np.where(flooded, 1.0, 0.0),
            method="hand-built",
        ),
        population=np.where(flooded, pop, 0.0),
        shelters=tuple(
            Shelter(id=ch, name=f"Shelter {ch}", row=r, col=c, capacity=cap, cost=cost)
            for r, row in enumerate(rows)
            for c, ch in enumerate(row)
            if ch in shelters
            for cap, cost in [shelters[ch]]
        ),
    )


def open_plan(*shelter_ids: str, cost: float, sheltered: float) -> dict:
    return {
        "actions": [{"type": "open_shelter", "shelter_id": s} for s in shelter_ids],
        "claims": {"cost": cost, "people_sheltered": sheltered},
        "rationale": "test plan",
    }


def offline(shelter_id: str) -> dict:
    return {"type": "shelter_offline", "shelter_id": shelter_id}


def test_plan_shelters_affected_people_up_to_shelter_capacity():
    world = world_from_map(["~.A"], pop=10, shelters={"A": (6, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=100, sheltered=6)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    result = transcript.rounds[0].result
    assert result.people_affected == 10
    assert result.people_sheltered == 6
    assert result.people_unreached == 4
    assert result.cost == 100
    assert result.robustness == 0.6


def test_people_cut_off_by_flooding_cannot_reach_a_shelter():
    # Only the flooded cell next to dry land can get out; the other two are cut off.
    world = world_from_map(["~~~.A"], pop=10, shelters={"A": (100, 50)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=50, sheltered=10)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    result = transcript.rounds[0].result
    assert result.people_sheltered == 10
    assert result.people_unreached == 20


def test_people_beyond_travel_reach_are_unreached():
    world = world_from_map(["~....A"], pop=10, shelters={"A": (100, 50)})
    world = replace(world, reach_cells=3)

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=50, sheltered=0)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    assert transcript.rounds[0].result.people_sheltered == 0


def test_an_attack_takes_effect_in_the_next_round():
    world = world_from_map(["A.~.B"], pop=10, shelters={"A": (10, 100), "B": (10, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=100, sheltered=10)]),
        ScriptedAdversary([offline("A")]),
        rounds=2,
    )

    first, second = transcript.rounds
    assert first.result.people_sheltered == 10
    assert second.scenario.offline_shelters == {"A"}
    assert second.result.people_sheltered == 0


def test_a_plan_with_correct_claims_passes_verification():
    world = world_from_map(["~.A"], pop=10, shelters={"A": (6, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=100, sheltered=6)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    assert transcript.rounds[0].verdict.passed


def test_a_plan_claiming_more_people_sheltered_than_it_achieves_fails_verification():
    # Shelter A has room for 20, but only 10 people are affected.
    world = world_from_map(["~.A"], pop=10, shelters={"A": (20, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=100, sheltered=15)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    verdict = transcript.rounds[0].verdict
    assert not verdict.passed
    failed = [c for c in verdict.checks if not c.passed]
    assert [(c.name, c.claimed, c.actual) for c in failed] == [("people_sheltered", 15, 10)]


def failed_checks(transcript, round_index=0) -> list[str]:
    return [c.name for c in transcript.rounds[round_index].verdict.checks if not c.passed]


def test_a_plan_over_budget_fails_verification():
    world = world_from_map(["~.A"], pop=10, shelters={"A": (10, 500)})

    transcript = run_proofloop(
        world,
        Scenario(budget=400),
        ScriptedPlanner([open_plan("A", cost=500, sheltered=10)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    assert failed_checks(transcript) == ["budget"]


def test_a_plan_claiming_more_than_its_shelters_can_hold_fails_capacity():
    # Claim matches nothing a capacity-6 shelter can do, so both checks fail.
    world = world_from_map(["~.A"], pop=10, shelters={"A": (6, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=100, sheltered=8)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    assert failed_checks(transcript) == ["people_sheltered", "capacity"]


def test_a_plan_opening_an_unknown_or_offline_shelter_fails_verification():
    world = world_from_map(["~.A.B"], pop=10, shelters={"A": (10, 100), "B": (10, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000, offline_shelters=frozenset({"B"})),
        ScriptedPlanner([open_plan("A", "B", "Z", cost=200, sheltered=10)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    shelter_checks = [
        c for c in transcript.rounds[0].verdict.checks if c.name == "shelters_available"
    ]
    assert [(c.passed, c.reason) for c in shelter_checks] == [
        (False, "shelter B is offline; unknown shelter Z")
    ]


def test_recommends_the_verified_plan_that_best_survives_all_attacks():
    # C is out of travel reach, so a plan relying on it shelters nobody.
    shelters = {"A": (10, 100), "B": (10, 100), "C": (10, 100)}
    world = replace(world_from_map(["A.~.B.....C"], pop=10, shelters=shelters), reach_cells=2)

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner(
            [
                open_plan("A", "B", cost=200, sheltered=10),
                open_plan("C", cost=100, sheltered=0),
            ]
        ),
        ScriptedAdversary([offline("A"), offline("A")]),
        rounds=2,
    )

    assert transcript.final_scenario.offline_shelters == {"A"}
    assert transcript.recommendation.round_index == 0
    assert transcript.recommendation.result.people_sheltered == 10


def test_never_recommends_a_plan_that_failed_verification():
    shelters = {"A": (10, 100), "B": (5, 100), "S": (10, 100)}
    world = world_from_map(["A.~.B.S"], pop=10, shelters=shelters)

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner(
            [
                open_plan("A", cost=100, sheltered=999),  # shelters 10 but lies about it
                open_plan("B", cost=100, sheltered=5),
            ]
        ),
        ScriptedAdversary([offline("S")]),
        rounds=2,
    )

    assert transcript.recommendation.round_index == 1


def test_malformed_planner_output_is_recorded_and_the_round_falls_back_to_the_best_plan():
    world = world_from_map(["A.~.S"], pop=10, shelters={"A": (10, 100), "S": (10, 100)})
    good = open_plan("A", cost=100, sheltered=10)

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([good, {"actions": [{"type": "evacuate_by_helicopter"}]}]),
        ScriptedAdversary([offline("S")]),
        rounds=2,
    )

    second = transcript.rounds[1]
    assert "evacuate_by_helicopter" in second.planner_error
    assert second.plan == transcript.rounds[0].plan
    assert second.result.people_sheltered == 10


def test_malformed_planner_output_in_the_first_round_leaves_the_round_without_a_plan():
    world = world_from_map(["A.~"], pop=10, shelters={"A": (10, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner(["not json at all"]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
    )

    first = transcript.rounds[0]
    assert first.planner_error
    assert first.plan is None
    assert first.result is None
    assert transcript.recommendation is None


def test_a_failing_agent_is_recorded_rather_than_crashing_the_run():
    class BrokenAdversary:
        def attack(self, world, scenario, plan, result):
            raise TimeoutError("model did not answer")

    world = world_from_map(["A.~"], pop=10, shelters={"A": (10, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=100, sheltered=10)]),
        BrokenAdversary(),
        rounds=2,
    )

    assert transcript.rounds[0].adversary_error == "TimeoutError: model did not answer"
    assert transcript.final_adversary_error == "TimeoutError: model did not answer"
    assert transcript.final_scenario == transcript.base_scenario


def test_runs_three_rounds_by_default():
    world = world_from_map(["A.~.S"], pop=10, shelters={"A": (10, 100), "S": (10, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=100, sheltered=10)]),
        ScriptedAdversary([offline("S")]),
    )

    assert [r.index for r in transcript.rounds] == [0, 1, 2]


def test_the_final_attack_lands_after_the_last_round_and_is_reported_separately():
    world = world_from_map(["A.~.B"], pop=10, shelters={"A": (10, 100), "B": (10, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", "B", cost=200, sheltered=10)]),
        ScriptedAdversary([offline("A"), offline("B")]),
        rounds=2,
    )

    assert [r.attack.shelter_id if r.attack else None for r in transcript.rounds] == ["A", None]
    assert transcript.final_attack.shelter_id == "B"
    assert transcript.final_scenario.offline_shelters == {"A", "B"}
    assert transcript.recommendation.result.people_sheltered == 0


def test_an_attack_on_an_unknown_shelter_is_rejected():
    world = world_from_map(["A.~"], pop=10, shelters={"A": (10, 100)})

    transcript = run_proofloop(
        world,
        Scenario(budget=1000),
        ScriptedPlanner([open_plan("A", cost=100, sheltered=10)]),
        ScriptedAdversary([offline("Z")]),
        rounds=2,
    )

    first = transcript.rounds[0]
    assert first.attack is None
    assert "unknown shelter Z" in first.adversary_error
    assert transcript.rounds[1].scenario == transcript.base_scenario
