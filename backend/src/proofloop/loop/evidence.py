"""Evidence trail: where every figure in a scored plan comes from.

Each figure gets its sources, the formula code applies, this plan's inputs, and
the assumptions and limitations behind it. Built by code from the same Trace the
score came from, so the trail never disagrees with the number.
"""

from proofloop.loop.describe import describe_action, describe_damage
from proofloop.loop.schemas import (
    AllocateBudget,
    Evidence,
    OpenShelter,
    Plan,
    Scenario,
    SourceRef,
    StageTransport,
)
from proofloop.loop.simulation import Trace, action_cost, billable
from proofloop.sources import source
from proofloop.world import FloodKind, World

RADAR_LIMITATION = (
    "The flood layer is radar-observed water change with a confidence per cell, "
    "not an official flood map."
)
SHELTER_COST_ASSUMPTION = (
    "A shelter costs $25 per space for a three-day activation (staff, cots, meals); "
    "the state shelter plan publishes no costs."
)
_METERS_PER_DEGREE = 111_320.0


def explain(
    world: World, scenario: Scenario, plan: Plan, trace: Trace, base: Scenario
) -> dict[str, Evidence]:
    """Evidence for each figure of `trace.result`, plus "budget". `base` is the starting
    scenario, before any attack."""
    figures = _Figures(world, scenario, plan, trace, base)
    return {
        "people_affected": figures.people_affected(),
        "people_sheltered": figures.people_sheltered(),
        "people_unreached": figures.people_unreached(),
        "robustness": figures.robustness(),
        "cost": figures.cost(),
        "unfunded_actions": figures.unfunded_actions(),
        "budget": figures.budget(),
    }


def cell_size_m(world: World) -> float:
    latitude = world.grid.latitude
    return abs(float(latitude[1] - latitude[0])) * _METERS_PER_DEGREE if latitude.size > 1 else 0.0


def people(count: float) -> str:
    return f"{count:,.0f}"


def money(amount: float) -> str:
    return f"${amount:,.0f}"


def sentence(text: str) -> str:
    """Capitalize only the first letter, keeping names like "Shelter A" intact."""
    return text[:1].upper() + text[1:]


def _refs(*ids: str) -> list[SourceRef]:
    return [SourceRef(id=s.id, title=s.title, origin=s.origin) for s in map(source, ids)]


class _Figures:
    def __init__(
        self, world: World, scenario: Scenario, plan: Plan, trace: Trace, base: Scenario
    ) -> None:
        self.world = world
        self.scenario = scenario
        self.plan = plan
        self.trace = trace
        self.base = base
        self.result = trace.result

    def people_affected(self) -> Evidence:
        hazard = self.world.hazard
        flagged = int(hazard.flooded.sum())
        inputs = [f"{flagged:,} of {hazard.flooded.size:,} cells flagged as flooded"]
        town = self.world.community(self.scenario.scope) if self.scenario.scope else None
        if town:
            radius_km = town.radius_cells * cell_size_m(self.world) / 1000
            inputs.append(
                f"Plan for {town.name} only: {people(self.result.people_affected)} people live "
                f"in flagged cells within {radius_km:.0f} km of its center"
            )
        else:
            inputs.append(f"{people(self.result.people_affected)} people live in them")
        if hazard.kind is not None:
            canopy = int((hazard.kind == FloodKind.UNDER_CANOPY).sum())
            inputs.append(f"{canopy:,} flagged cells are under tree canopy, the rest open water")
        return Evidence(
            sources=_refs("S1", "S6"),
            formula=(
                f"Sum of the residents of every flagged cell (about {cell_size_m(self.world):.0f}"
                f" m across). {self._flag_rule()}"
            ),
            inputs=inputs,
            assumptions=[
                "Everyone who lives in a flagged cell is affected; nobody outside one is.",
                "Each 2020 Census block's people are spread evenly over the cells it covers.",
            ],
            limitations=[
                RADAR_LIMITATION,
                "One radar pass about a day after landfall: water that drained before it, "
                "or arrived after it, is missed.",
                "Most flagged cells are brightening under tree canopy; some may be radar "
                "speckle or wet fields rather than flooding.",
                "Counts 2020 residents, not who was home during the storm.",
            ],
        )

    def people_sheltered(self) -> Evidence:
        reach_km = self.world.reach_cells * cell_size_m(self.world) / 1000
        return Evidence(
            sources=_refs("S3", "S4", "S1", "S6"),
            formula=(
                "Each open shelter takes the nearest affected people who can reach it through "
                f"dry cells within {reach_km:.0f} km ({self.world.reach_cells:,} cell steps), up "
                "to its capacity; shelters fill in plan order and nobody is counted twice. "
                "Staged transport then carries a community's remaining people, nearest its "
                "center first, into beds still free."
            ),
            inputs=self._placement_inputs(),
            assumptions=[
                "People move cell to cell (up, down, left, right) over dry land; the road "
                "network is not modeled.",
                "Everyone who can reach an open shelter goes.",
                "Shelter capacities are the general-population spaces in the 2020 state plan.",
            ],
            limitations=[
                RADAR_LIMITATION,
                "Distance is counted in grid steps, not driving time or road conditions.",
                "A closed road stops a town's people leaving on their own; it does not block "
                "travel through the town.",
            ],
        )

    def people_unreached(self) -> Evidence:
        r = self.result
        inputs = [
            f"{people(r.people_affected)} affected − {people(r.people_sheltered)} sheltered "
            f"= {people(r.people_unreached)} unreached"
        ]
        return Evidence(
            sources=_refs("S4", "S1", "S6"),
            formula="People affected minus people sheltered: those no open shelter or "
            "transport takes.",
            inputs=inputs,
            assumptions=["Everyone sheltered is counted once, in the first place that takes them."],
            limitations=[
                RADAR_LIMITATION,
                "Unreached is not stranded: some may leave on their own or ride out the "
                "storm safely.",
            ],
        )

    def robustness(self) -> Evidence:
        r = self.result
        damage = describe_damage(self.scenario, self.world)
        return Evidence(
            sources=_refs("S4"),
            formula="People sheltered divided by people affected, under these conditions.",
            inputs=[
                f"{people(r.people_sheltered)} ÷ {people(r.people_affected)} = {r.robustness:.0%}",
                f"In effect: {damage}" if damage else "No attacks in effect",
                f"Budget {money(self.scenario.budget)}",
            ],
            assumptions=["Every affected person counts the same."],
            limitations=[
                RADAR_LIMITATION,
                "Scores one set of conditions; it is not a probability that the plan works.",
            ],
        )

    def cost(self) -> Evidence:
        lines = [
            f"{sentence(describe_action(a, self.world))}: {money(action_cost(self.world, a))}"
            for a in billable(self.plan.actions)
        ]
        return Evidence(
            sources=_refs("S3", "S4"),
            formula=(
                "Sum of the plan's action costs. A shelter opened twice is paid once; a "
                "contingency reserve counts toward cost though it is held back, not spent."
            ),
            inputs=[*lines, f"Total: {money(self.result.cost)}"],
            assumptions=[
                SHELTER_COST_ASSUMPTION,
                f"Staged transport costs {money(self.world.transport_cost_per_seat)} per seat.",
            ],
            limitations=["Costs are planning assumptions, not quotes or published figures."],
        )

    def unfunded_actions(self) -> Evidence:
        spending = [a for a in billable(self.plan.actions) if not isinstance(a, AllocateBudget)]
        unfunded = spending[len(spending) - self.result.unfunded_actions :]
        dropped = [sentence(describe_action(a, self.world)) for a in unfunded]
        return Evidence(
            sources=_refs("S4"),
            formula=(
                "Actions are funded in plan order while their running cost fits the budget; "
                "the first that does not fit, and every later one, get no money. A contingency "
                "reserve is held back, so it needs no funding."
            ),
            inputs=[f"Budget {money(self.scenario.budget)}", *(f"Unfunded: {d}" for d in dropped)],
            assumptions=["The plan lists its most important actions first."],
            limitations=["No partial funding: each action is paid in full or not at all."],
        )

    def budget(self) -> Evidence:
        inputs = [f"Starting budget {money(self.base.budget)}"]
        if self.scenario.budget < self.base.budget:
            cut = 1 - self.scenario.budget / self.base.budget if self.base.budget else 0.0
            inputs.append(f"After cuts {money(self.scenario.budget)} ({cut:.0%} less)")
        return Evidence(
            sources=_refs("S4"),
            formula="The starting budget, reduced by each budget cut made so far.",
            inputs=inputs,
            assumptions=["Cuts compound: each applies to what earlier cuts left."],
            limitations=["A cut lands all at once; real cuts may arrive in stages."],
        )

    def _flag_rule(self) -> str:
        method = self.world.hazard.method
        if method == "gcov":
            return (
                "A cell is flagged when its radar backscatter change between the Sep 28 and "
                "Oct 10 passes reaches half of a strong 6 dB change: darkening into open water, "
                "or brightening under tree canopy beyond the scene's typical change."
            )
        if method == "sme2":
            return (
                "A cell is flagged when its radar change or soil-moisture wetting between the "
                "Sep 28 and Oct 10 passes reaches half of a strong change."
            )
        return f"Cells are flagged by the {method} hazard layer."

    def _placement_inputs(self) -> list[str]:
        world, scenario, trace = self.world, self.scenario, self.trace
        inputs: list[str] = []
        for action in trace.funded:
            if isinstance(action, OpenShelter) and (shelter := world.shelter(action.shelter_id)):
                if shelter.id in scenario.offline_shelters:
                    inputs.append(f"{shelter.name} is offline")
                elif shelter.id in trace.walked:
                    walked = float(trace.walked[shelter.id].people.sum())
                    inputs.append(
                        f"{shelter.name}: {people(shelter.capacity)} spaces, "
                        f"{people(walked)} people reach it on their own"
                    )
        for action in trace.funded:
            if isinstance(action, StageTransport):
                moved = sum(
                    c.people for c in trace.carried if c.community_id == action.community_id
                )
                town = world.community(action.community_id)
                name = town.name if town else action.community_id
                inputs.append(
                    f"Transport for {name}: {action.seats} seats, {people(moved)} people carried"
                )
        for community_id in sorted(scenario.closed_communities):
            town = world.community(community_id)
            inputs.append(f"Road into {town.name if town else community_id} closed")
        return inputs
