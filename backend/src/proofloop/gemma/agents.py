"""Gemma 4 Planner and Adversary.

Both see the same facts the Simulation uses: shelters (capacity, cost, availability
and how many affected people each can reach on its own), communities (affected
people and whether their road is open), the budget and the transport price. The
Planner also sees the Verifier's findings from earlier rounds.

The Planner has a check step: it drafts a plan, code simulates the draft, and it
writes its final plan and claims knowing what the draft achieved. If the final
plan would still fail verification (over budget or wrong claims), it gets one
more check with the exact numbers. The Verifier still checks the result.
"""

import re
from collections.abc import Sequence
from typing import Annotated

from pydantic import Field

from proofloop.gemma.client import GemmaClient, Generation
from proofloop.gemma.sources import source_pack
from proofloop.loop.agents import AgentReply
from proofloop.loop.describe import describe_action, describe_attack, describe_damage
from proofloop.loop.schemas import (
    Attack,
    BudgetCut,
    Plan,
    RoadClosed,
    Round,
    Scenario,
    ShelterOffline,
    SimulationResult,
)
from proofloop.loop.simulation import action_cost, simulate
from proofloop.loop.verifier import verify
from proofloop.world import Community, World

PLANNER_SYSTEM = """You are the Planner for a county emergency manager after a hurricane.
Shelter as many affected people as possible within the budget, with a plan that still
works after a red team knocks out a shelter, closes a road or cuts the budget.

Actions (use any mix, in priority order; earlier actions are funded first):
- open_shelter(shelter_id): people who can reach it on their own go there.
- stage_transport(community_id, seats): high-water vehicles carry up to `seats` of that
  community's remaining affected people into open shelters with spare beds, even if its
  road is closed. Costs {seat_cost} per seat.
- allocate_budget(contingency_reserve, amount): money held back (at least $1,000). If the
  budget is cut later, the reserve absorbs the cut before any action loses funding.
- target_outreach(community_id): door-to-door teams and alerts warn that community's
  people flooded outside FEMA flood zones. Costs {outreach_cost}. It matters once those
  people are unwarned: without outreach they think they are safe and stay home.

Rules:
- Only use shelters and communities from the lists, and never a shelter marked OFFLINE.
- Total cost (all actions, including any reserve) must never exceed the budget, even if
  that means sheltering fewer people. A plan over budget is rejected outright.
- Claims are checked by exact simulation. claims.cost is the total cost of all actions.
  claims.people_sheltered must match the simulation within 1%: a shelter takes at most
  its capacity, people reachable from several shelters are counted once, and transport
  only fills beds the shelters you open still have free.
- If an earlier round's claims were rejected, learn from the recomputed numbers.
- You get one simulation check of a draft before your final answer. If you change
  the actions after the check, your claims must be your own best estimate.
- rationale: two or three sentences for the emergency manager, naming shelters and
  communities by name (not id) and citing sources as [S1], [S2].

Sources:
{sources}"""

ADVERSARY_SYSTEM = """You are the Adversary, a red team testing a hurricane response plan.
Choose exactly one attack that leaves the plan sheltering as few people as possible:
- shelter_offline(shelter_id): power loss, flooding or a staff shortage closes a shelter.
- road_closed(community_id): flooding or debris cuts a community's road, so its people
  cannot reach a shelter on their own (transport still gets through).
- budget_cut(percent, 10 to 50): the county loses money; actions the smaller budget
  cannot fund are dropped, last first, after any contingency reserve is used up.
- unwarned_outside_zone(): people flooded outside FEMA flood zones believe they are
  safe (and likely have no flood insurance), so they stay home unless the plan runs
  outreach in their community. Strong when many affected people live outside the zones.
Prefer what the plan relies on most. Only use shelters and communities from the lists.
rationale: one or two sentences on why this could happen and why it hurts, naming
shelters and communities by name (not id) and citing sources as [S1], [S2].

Sources:
{sources}"""


_ATTACKS_ONCE_UNWARNED = Annotated[
    ShelterOffline | RoadClosed | BudgetCut, Field(discriminator="type")
]


class GemmaPlanner:
    def __init__(self, client: GemmaClient):
        self._client = client

    def propose(self, world: World, scenario: Scenario, history: Sequence[Round]) -> AgentReply:
        system = PLANNER_SYSTEM.format(
            sources=source_pack(),
            seat_cost=f"${world.transport_cost_per_seat:,.0f}",
            outreach_cost=f"${world.outreach_cost:,.0f}",
        )
        # Transport only makes sense where people are affected.
        allowed = {**_allowed(world, scenario), "community_id": _affected_communities(world)}
        situation = "\n\n".join([_situation(world, scenario), _history(history, world)])

        draft = self._client.generate(system, f"{situation}\n\nDraft a plan.", Plan, allowed)
        checked = simulate(world, scenario, draft.value)
        final = self._client.generate(
            system,
            "\n\n".join(
                [situation, _check(draft.value, checked, scenario, world), "Give your final plan."]
            ),
            Plan,
            allowed,
        )
        skipped = draft.skipped + final.skipped

        failures = [c.reason for c in verify(world, scenario, final.value).checks if not c.passed]
        if failures:
            rechecked = simulate(world, scenario, final.value)
            final = self._client.generate(
                system,
                "\n\n".join(
                    [
                        situation,
                        _check(final.value, rechecked, scenario, world),
                        "Your plan would be rejected: " + "; ".join(failures) + ".",
                        "Fix it: stay within the budget and claim exactly the simulated numbers "
                        "for the actions you keep. Give your final plan.",
                    ]
                ),
                Plan,
                allowed,
            )
            skipped += final.skipped
        return _reply(final, world, skipped=skipped)


class GemmaAdversary:
    def __init__(self, client: GemmaClient):
        self._client = client

    def attack(
        self, world: World, scenario: Scenario, plan: Plan | None, result: SimulationResult | None
    ) -> AgentReply:
        lines = [_situation(world, scenario)]
        if plan and result:
            lines.append(
                f"The plan will {_actions(plan, world)}. It shelters "
                f"{result.people_sheltered:.0f} of {result.people_affected:.0f} affected people "
                f"and costs ${result.cost:,.0f}."
            )
        in_effect = describe_damage(scenario, world)
        if in_effect:
            lines.append(f"Already in effect (do not repeat): {in_effect}.")
        lines.append("Choose one attack.")
        allowed = {"shelter_id": _allowed(world, scenario)["shelter_id"]}
        if open_roads := [
            c.id for c in world.communities if c.id not in scenario.closed_communities
        ]:
            allowed["community_id"] = open_roads
        # Once people are unwarned, that attack is no longer on offer.
        menu = _ATTACKS_ONCE_UNWARNED if scenario.unwarned_outside_zones else Attack
        generation = self._client.generate(
            ADVERSARY_SYSTEM.format(sources=source_pack()), "\n\n".join(lines), menu, allowed
        )
        return _reply(generation, world, skipped=generation.skipped)


def _reply(generation: Generation, world: World, skipped: list[str]) -> AgentReply:
    output = generation.value.model_dump()
    output["rationale"] = _with_shelter_names(output["rationale"], world)
    return AgentReply(
        output=output,
        model=generation.model,
        provider=generation.provider,
        skipped=skipped,
    )


def _with_shelter_names(text: str, world: World) -> str:
    """Gemma sometimes cites places by id despite the prompt; show their names instead."""
    places = [(s.id, s.name) for s in world.shelters] + [(c.id, c.name) for c in world.communities]
    for place_id, name in sorted(places, key=lambda p: len(p[0]), reverse=True):
        text = re.sub(rf"\b{re.escape(place_id)}\b", name, text)
    return text


def _actions(plan: Plan, world: World) -> str:
    return "; ".join(describe_action(a, world) for a in plan.actions) or "do nothing"


def _situation(world: World, scenario: Scenario) -> str:
    affected = simulate(world, scenario, _single_shelter_plan(None)).people_affected
    rows = []
    for shelter in world.shelters:
        if shelter.id in scenario.offline_shelters:
            rows.append(f"- id {shelter.id} ({shelter.name}): OFFLINE")
            continue
        alone = simulate(world, scenario, _single_shelter_plan(shelter.id)).people_sheltered
        rows.append(
            f"- id {shelter.id} ({shelter.name}): capacity {shelter.capacity:.0f}, "
            f"cost ${shelter.cost:,.0f}, can shelter {alone:.0f} people on its own"
        )
    towns = []
    for community in world.communities:
        people = _affected_in(world, community)
        outside = _affected_in(world, community, outside_zones_only=True)
        road = "road CLOSED" if community.id in scenario.closed_communities else "road open"
        towns.append(
            f"- id {community.id} ({community.name}): {people:.0f} affected "
            f"({outside:.0f} outside FEMA flood zones), {road}"
        )
    return "\n".join(
        [
            f"Affected people: {affected:.0f}. Budget: ${scenario.budget:,.0f}. "
            f"Transport: ${world.transport_cost_per_seat:,.0f} per seat. "
            f"Outreach: ${world.outreach_cost:,.0f} per community.",
            *(
                [
                    "People flooded outside FEMA flood zones are UNWARNED: they stay home "
                    "unless the plan runs outreach in their community."
                ]
                if scenario.unwarned_outside_zones
                else []
            ),
            "Shelters (refer to them by id):",
            *rows,
            *(["Communities (refer to them by id):", *towns] if towns else []),
        ]
    )


def _check(draft: Plan, result: SimulationResult, scenario: Scenario, world: World) -> str:
    check = (
        f"Simulation check of your draft ({_actions(draft, world)}): "
        f"cost ${result.cost:,.0f}, shelters {result.people_sheltered:.0f} of "
        f"{result.people_affected:.0f} affected people "
        f"(you claimed ${draft.claims.cost:,.0f} and {draft.claims.people_sheltered:.0f}). "
        f"{result.people_unreached_outside_zones:.0f} unreached people live outside FEMA "
        "flood zones. "
        f"Cost of each action: {_cost_breakdown(draft, world)}; total ${result.cost:,.0f}. "
        "Your final claims.cost must be the total for your final actions."
    )
    if result.cost > scenario.budget:
        return (
            f"{check} The draft is OVER BUDGET by ${result.cost - scenario.budget:,.0f}. "
            f"Your final plan must cost at most ${scenario.budget:,.0f}; drop or shrink actions."
        )
    return f"{check} Keep the draft or improve it."


def _cost_breakdown(plan: Plan, world: World) -> str:
    return "; ".join(
        f"{describe_action(a, world)} ${action_cost(world, a):,.0f}" for a in plan.actions
    )


def _affected_communities(world: World) -> list[str]:
    return [c.id for c in world.communities if _affected_in(world, c) > 0]


def _affected_in(world: World, community: Community, outside_zones_only: bool = False) -> float:
    flooded = world.flooded_outside_fema_zones() if outside_zones_only else world.hazard.flooded
    cells = community.mask(world.grid.shape) & flooded
    return float(world.population[cells].sum())


def _allowed(world: World, scenario: Scenario) -> dict[str, list[str]]:
    allowed = {
        "shelter_id": [s.id for s in world.shelters if s.id not in scenario.offline_shelters]
    }
    if world.communities:
        allowed["community_id"] = [c.id for c in world.communities]
    return allowed


def _history(history: Sequence[Round], world: World) -> str:
    if not history:
        return "This is the first round."
    lines = ["Earlier rounds:"]
    for round_ in history:
        did = _actions(round_.plan, world) if round_.plan else "no valid plan"
        line = f"- Round {round_.index + 1}: {did}"
        if round_.result:
            line += f", sheltered {round_.result.people_sheltered:.0f}"
        if round_.verdict and not round_.verdict.passed:
            failed = "; ".join(c.reason or c.name for c in round_.verdict.checks if not c.passed)
            line += f". REJECTED by the Verifier: {failed}"
        if round_.attack:
            line += f". Then {describe_attack(round_.attack, world)}"
        lines.append(line + ".")
    return "\n".join(lines)


def _single_shelter_plan(shelter_id: str | None) -> Plan:
    """A plan opening one shelter, or none, for asking the Simulation what it achieves."""
    actions = [{"type": "open_shelter", "shelter_id": shelter_id}] if shelter_id else []
    return Plan.model_validate({"actions": actions, "claims": {"cost": 0, "people_sheltered": 0}})
