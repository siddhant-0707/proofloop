"""A plan written up as an operations plan, by code templates.

Sections follow the FEMA CPG 101 base-plan headings that Florida county plans also use,
with ICS 202-style objectives and ICS 204-style assignments (docs/research/plan-report-format.md).
Code writes purpose and scope, situation overview, planning assumptions, objectives and
concept of operations; the assignments, budget, briefing, limitations and references are
data the web app lays out. Every number comes from the same simulation trace that scored
the plan.
"""

from proofloop.loop.briefing import brief
from proofloop.loop.describe import describe_damage
from proofloop.loop.evidence import RADAR_LIMITATION, cell_size_m, explain, money, people
from proofloop.loop.schemas import (
    AllocateBudget,
    Assignment,
    Briefing,
    OpenShelter,
    Plan,
    PlanReport,
    ReportSection,
    Scenario,
    StageTransport,
)
from proofloop.loop.simulation import Trace, action_cost, billable, trace
from proofloop.world import World

AREA_NAME = "Dixie and Taylor counties"


def write_report(world: World, scenario: Scenario, plan: Plan, base: Scenario) -> PlanReport:
    """`scenario` is the conditions the report is written for; `base` is the starting
    scenario, before any attack."""
    traced = trace(world, scenario, plan)
    evidence = explain(world, scenario, plan, traced, base)
    briefing = brief(world, scenario, traced)
    assignments = _assignments(world, scenario, plan, traced, briefing)
    return PlanReport(
        title=f"Shelter and evacuation plan: {_place(world, scenario)}",
        scenario=scenario,
        result=traced.result,
        sections=[
            ReportSection(title="Purpose and scope", lines=_purpose(world, scenario)),
            ReportSection(title="Situation overview", lines=_situation(world, scenario, traced)),
            ReportSection(
                title="Planning assumptions",
                lines=_unique(a for e in evidence.values() for a in e.assumptions),
            ),
            ReportSection(title="Objectives", lines=_objectives(scenario, traced, assignments)),
            ReportSection(title="Concept of operations", lines=_concept(assignments)),
        ],
        assignments=assignments,
        briefing=briefing,
        evidence=evidence,
        limitations=_unique(
            [RADAR_LIMITATION, *(lim for e in evidence.values() for lim in e.limitations)]
        ),
        references=list({s.id: s for e in evidence.values() for s in e.sources}.values()),
    )


def _place(world: World, scenario: Scenario) -> str:
    town = world.community(scenario.scope) if scenario.scope else None
    return town.name if town else AREA_NAME


def _purpose(world: World, scenario: Scenario) -> list[str]:
    town = world.community(scenario.scope) if scenario.scope else None
    if town:
        km = town.radius_cells * cell_size_m(world) / 1000
        covered = (
            f"People affected: everyone in radar-flagged cells within {km:.0f} km of the "
            f"{town.name} center. Any public shelter in the two counties may take them."
        )
    else:
        covered = "People affected: everyone in radar-flagged cells in the two counties."
    return [
        "Shelter the people living where Hurricane Isaias flooded, within the budget, by "
        "opening shelters and staging high-water transport.",
        f"Area: {_place(world, scenario)}, Florida.",
        covered,
        "Not covered: medical evacuation, special-needs and pet-friendly sheltering, clearance "
        "times and re-entry.",
    ]


def _situation(world: World, scenario: Scenario, traced: Trace) -> list[str]:
    affected = traced.result.people_affected
    lines = [
        "NISAR radar imaged the area on Sep 28 and Oct 10, 2026, about a day after Hurricane "
        "Isaias made landfall; the second pass shows where water changed.",
        f"{people(affected)} people live in radar-flagged cells in {_place(world, scenario)}.",
    ]
    open_shelters = [s for s in world.shelters if s.id not in scenario.offline_shelters]
    capacity = sum(s.capacity for s in open_shelters)
    lines.append(
        f"{len(open_shelters)} public shelters are available, with {people(capacity)} spaces: "
        + ", ".join(f"{s.name} ({people(s.capacity)})" for s in open_shelters)
        + "."
    )
    lines.append(f"Budget: {money(scenario.budget)}.")
    damage = describe_damage(scenario, world)
    if damage:
        lines.append(f"In effect: {damage}.")
    return lines


def _objectives(scenario: Scenario, traced: Trace, assignments: list[Assignment]) -> list[str]:
    r = traced.result
    objectives = [
        f"Shelter {people(r.people_sheltered)} of the {people(r.people_affected)} affected "
        f"people ({r.robustness:.0%})."
    ]
    funded = [a for a in assignments if a.funded]
    if rides := [a for a in funded if a.kind == "transport"]:
        carried = sum(a.people or 0 for a in rides)
        objectives.append(
            f"Carry about {people(carried)} people who cannot reach a shelter on their own."
        )
    if reserve := [a for a in funded if a.kind == "reserve"]:
        objectives.append(f"Hold {money(reserve[0].cost)} in reserve against budget cuts.")
    objectives.append(
        f"Stay within the {money(scenario.budget)} budget (the plan costs {money(r.cost)})."
    )
    return objectives


def _concept(assignments: list[Assignment]) -> list[str]:
    funded = [a for a in assignments if a.funded]
    steps: list[str] = []
    if shelters := [a for a in funded if a.kind == "shelter"]:
        names = _join([a.title.removeprefix("Open ") for a in shelters])
        steps.append(
            f"Sheltering: open {names}, in that order. Each takes the nearest affected people "
            "who can reach it over dry land, up to its capacity."
        )
    if rides := [a for a in funded if a.kind == "transport"]:
        towns = _join([a.title.removeprefix("Transport for ") for a in rides])
        steps.append(
            f"Transport: high-water vehicles carry the people left in {towns} into the beds "
            "still free, nearest the town center first, even if the road is closed."
        )
    if [a for a in funded if a.kind == "reserve"]:
        steps.append(
            "Reserve: money held back is released first if the budget is cut, before any "
            "action loses funding."
        )
    if dropped := [a for a in assignments if not a.funded]:
        steps.append("Not funded within the budget: " + _join([a.title for a in dropped]) + ".")
    return steps or ["The plan takes no action."]


def _assignments(
    world: World, scenario: Scenario, plan: Plan, traced: Trace, briefing: Briefing
) -> list[Assignment]:
    actions = billable(plan.actions)
    spending = [a for a in actions if not isinstance(a, AllocateBudget)]
    unfunded = {id(a) for a in spending[len(spending) - traced.result.unfunded_actions :]}
    assignments: list[Assignment] = []
    for action in actions:
        cost = action_cost(world, action)
        is_funded = id(action) not in unfunded
        if isinstance(action, OpenShelter):
            assignments.append(_shelter(world, scenario, action, traced, briefing, cost, is_funded))
        elif isinstance(action, StageTransport):
            town = world.community(action.community_id)
            name = town.name if town else action.community_id
            rides = [c for c in traced.carried if c.community_id == action.community_id]
            carried = sum(c.people for c in rides)
            to = [s.name for c in rides if (s := world.shelter(c.shelter_id))]
            assignments.append(
                Assignment(
                    kind="transport",
                    title=f"Transport for {name}",
                    resource=f"{action.seats} high-water seats",
                    work=(
                        f"Stage at the {name} center and carry about {people(carried)} people, "
                        "nearest the center first"
                        + (f", to {_join(to)}." if to else "; no shelter has beds left for them.")
                    ),
                    people=carried,
                    cost=cost,
                    funded=is_funded,
                )
            )
        else:
            assert isinstance(action, AllocateBudget)
            assignments.append(
                Assignment(
                    kind="reserve",
                    title="Contingency reserve",
                    resource=money(action.amount),
                    work="Hold back; released first if the budget is cut.",
                    cost=cost,
                    funded=True,
                )
            )
    return assignments


def _shelter(
    world: World,
    scenario: Scenario,
    action: OpenShelter,
    traced: Trace,
    briefing: Briefing,
    cost: float,
    funded: bool,
) -> Assignment:
    shelter = world.shelter(action.shelter_id)
    name = shelter.name if shelter else action.shelter_id
    capacity = shelter.capacity if shelter else 0.0
    if action.shelter_id in scenario.offline_shelters:
        work = "Offline under these conditions: it takes nobody."
        arrivals = 0.0
    else:
        walked = traced.walked.get(action.shelter_id)
        arrivals = float(walked.people.sum()) if walked else 0.0
        arrivals += sum(c.people for c in traced.carried if c.shelter_id == action.shelter_id)
        towns = [
            f"{n.name if n.community_id else 'outside the towns'} ({people(a.people)})"
            for n in briefing.neighborhoods
            for a in n.shelters
            if a.shelter_id == action.shelter_id
        ]
        if arrivals < 0.5:
            work = (
                f"Open and staff for {people(capacity)} on standby: nobody needs it under these "
                "conditions, but it takes people if a shelter earlier in the plan fills or goes "
                "offline."
            )
        else:
            work = f"Open and staff for {people(capacity)}; expect about {people(arrivals)}" + (
                f", from {_join(towns)}." if towns else "."
            )
    return Assignment(
        kind="shelter",
        title=f"Open {name}",
        resource=f"{people(capacity)} spaces",
        work=work,
        people=arrivals,
        capacity=capacity,
        cost=cost,
        funded=funded,
    )


def _unique(items) -> list[str]:
    return list(dict.fromkeys(items))


def _join(items: list[str]) -> str:
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
