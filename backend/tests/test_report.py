"""The plan report, and how the recommendation is chosen from the candidates."""

from loop_worlds import (
    budget_cut,
    offline,
    open_plan,
    open_shelter,
    plan,
    reserve,
    transport,
    world_from_map,
)

from proofloop.loop import ScriptedAdversary, ScriptedPlanner, run_proofloop
from proofloop.loop.evidence import RADAR_LIMITATION
from proofloop.loop.schemas import Scenario

# Town S (cols 6-8) is too far to walk to A; town T (row 1) walks to A along the dry road.
WORLD = ["A.....~~~", "~o......."]
TOWNS = {"S": (0, 7, 1), "T": (1, 0, 1)}


def _world():
    return world_from_map(
        WORLD, pop=10, shelters={"A": (100, 100)}, communities=TOWNS, reach_cells=2
    )


def test_the_report_writes_the_plan_up_as_an_operations_plan():
    transcript = run_proofloop(
        _world(),
        Scenario(budget=20_000),
        ScriptedPlanner(
            [
                plan(
                    open_shelter("A"),
                    transport("S", 30),
                    reserve(1_000),
                    cost=5_600,
                    sheltered=50,
                )
            ]
        ),
        ScriptedAdversary([offline("A")]),
        rounds=1,
        final_attack=False,
    )

    report = transcript.recommendation.report
    assert report.title == "Shelter and evacuation plan: Dixie and Taylor counties"
    assert [s.title for s in report.sections] == [
        "Purpose and scope",
        "Situation overview",
        "Planning assumptions",
        "Objectives",
        "Concept of operations",
    ]
    assert "People affected: everyone in radar-flagged cells in the two counties." in (
        report.sections[0].lines
    )
    assert [(a.kind, a.title, a.people, a.cost, a.funded) for a in report.assignments] == [
        ("shelter", "Open Shelter A", 50, 100, True),
        ("transport", "Transport for Town S", 30, 4_500, True),
        ("reserve", "Contingency reserve", None, 1_000, True),
    ]
    assert [a.capacity for a in report.assignments] == [100, None, None]
    assert report.result.people_sheltered == 50
    assert RADAR_LIMITATION in report.limitations
    assert {s.id for s in report.references} >= {"S1", "S3", "S4", "S6"}


def test_actions_the_budget_cannot_fund_are_marked_in_the_report():
    transcript = run_proofloop(
        _world(),
        Scenario(budget=1_000),
        ScriptedPlanner([plan(open_shelter("A"), transport("S", 30), cost=4_600, sheltered=50)]),
        ScriptedAdversary([offline("A")]),
        rounds=1,
        final_attack=False,
    )

    # Over budget, so it fails verification and is only reported for its round.
    report = transcript.rounds[0].report
    assert [(a.title, a.funded) for a in report.assignments] == [
        ("Open Shelter A", True),
        ("Transport for Town S", False),
    ]
    concept = next(s for s in report.sections if s.title == "Concept of operations")
    assert "Not funded within the budget: Transport for Town S." in concept.lines


def test_candidates_are_the_verified_plans_and_the_best_is_recommended():
    world = world_from_map(["A.~.B"], pop=10, shelters={"A": (10, 100), "B": (10, 100)})
    transcript = run_proofloop(
        world,
        Scenario(budget=1_000),
        ScriptedPlanner(
            [
                open_plan("A", cost=100, sheltered=10),
                open_plan("A", cost=100, sheltered=99),  # wrong claim: rejected
                open_plan("B", cost=100, sheltered=10),
            ]
        ),
        ScriptedAdversary([budget_cut(10)]),
        rounds=3,
    )

    rec = transcript.recommendation
    assert [c.round_index for c in rec.candidates] == [0, 2, None]
    assert (
        rec.round_index
        == max(rec.candidates, key=lambda c: (c.result.robustness, c.typical)).round_index
    )
    assert rec.result == next(c for c in rec.candidates if c.round_index == rec.round_index).result
