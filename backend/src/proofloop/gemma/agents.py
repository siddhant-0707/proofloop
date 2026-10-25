"""Gemma 4 Planner and Adversary.

Both see the same facts the Simulation uses: shelters (capacity, cost, availability
and how many affected people each can reach on its own), communities (affected
people and whether their road is open), the budget and the transport price. The
Planner also sees earlier rounds: the Verifier's findings and each failure the
Adversary tested, so it can hedge. The Adversary sees only the plan it tests.

The Planner has a check step: it drafts a plan, code simulates the draft, and it
writes its final plan and claims knowing what the draft achieved. If the final
plan would still fail verification (over budget or wrong claims), it gets one
more check with the exact numbers. The Verifier still checks the result.
"""

import math
import re
from collections.abc import Sequence

from proofloop.gemma.client import GemmaClient, Generation
from proofloop.loop.agents import AgentReply
from proofloop.loop.describe import describe_action, describe_attack, describe_damage
from proofloop.loop.schemas import (
    AllocateBudget,
    Attack,
    OpenShelter,
    Plan,
    Round,
    Scenario,
    SimulationResult,
    StageTransport,
)
from proofloop.loop.simulation import action_cost, simulate
from proofloop.loop.verifier import verify
from proofloop.sources import source_pack
from proofloop.world import Community, World

PLANNER_SYSTEM = """You are the Planner for a county emergency manager after a hurricane.
First, shelter every affected person under the conditions given, if the budget allows;
otherwise as many as possible. A red team then tests each plan with one failure (a
shelter offline, a road closed, or a budget cut). Earlier rounds show the failures it
found: with any money left, hedge against them, but never shelter fewer people under the
conditions given. Plans are ranked first by people sheltered as given, then by the
average share sheltered under every single failure.

Actions (use any mix, in priority order; earlier actions are funded first):
- open_shelter(shelter_id): people who can reach it on their own go there.
- stage_transport(community_id, seats): high-water vehicles carry up to `seats` of that
  community's remaining affected people into open shelters with spare beds, even if its
  road is closed. Costs {seat_cost} per seat.
- allocate_budget(contingency_reserve, amount): money held back (at least $1,000). If the
  budget is cut later, the reserve absorbs the cut before any action loses funding.

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
Prefer what the plan relies on most. Only use shelters and communities from the lists.
rationale: one or two sentences on why this could happen and why it hurts, naming
shelters and communities by name (not id) and citing sources as [S1], [S2].

Sources:
{sources}"""


class GemmaPlanner:
    """`starting_plan`, for a re-plan, stands in for the first draft: Gemma adjusts the
    previous recommendation to the new conditions instead of planning from scratch."""

    def __init__(self, client: GemmaClient, starting_plan: Plan | None = None):
        self._client = client
        self._starting_plan = starting_plan

    def propose(self, world: World, scenario: Scenario, history: Sequence[Round]) -> AgentReply:
        system = PLANNER_SYSTEM.format(
            sources=source_pack(),
            seat_cost=f"${world.transport_cost_per_seat:,.0f}",
        )
        # Transport only makes sense where people are affected.
        allowed = {
            **_allowed(world, scenario),
            "community_id": _affected_communities(world, scenario),
        }
        situation = "\n\n".join([_situation(world, scenario), _history(history, world)])

        if self._starting_plan is not None and not history:
            draft_plan, skipped = self._starting_plan, []
            label = "your previous plan under the new conditions"
        else:
            draft = self._client.generate(system, f"{situation}\n\nDraft a plan.", Plan, allowed)
            draft_plan, skipped = draft.value, list(draft.skipped)
            label = "your draft"
        checked = simulate(world, scenario, draft_plan)
        final = self._client.generate(
            system,
            "\n\n".join(
                [
                    situation,
                    _check(draft_plan, checked, scenario, world, label),
                    "Give your final plan.",
                ]
            ),
            Plan,
            allowed,
        )
        skipped += final.skipped

        failures = [c.reason for c in verify(world, scenario, final.value).checks if not c.passed]
        if failures:
            rechecked = simulate(world, scenario, final.value)
            if rechecked.cost <= scenario.budget:
                # The actions fit: only the arithmetic is off, so say exactly what to claim.
                fix = (
                    "Your actions fit the budget. Keep exactly the same actions and set "
                    f"claims.cost = {rechecked.cost:.0f} and "
                    f"claims.people_sheltered = {rechecked.people_sheltered:.1f}."
                )
            else:
                fix = (
                    "Cut actions to fit the budget, then claim the simulated numbers for the "
                    "actions you keep."
                )
            final = self._client.generate(
                system,
                "\n\n".join(
                    [
                        situation,
                        _check(final.value, rechecked, scenario, world, "your final plan"),
                        "Your plan would be rejected: " + "; ".join(failures) + ".",
                        fix,
                        "Give your final plan.",
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
            c.id for c in _towns(world, scenario) if c.id not in scenario.closed_communities
        ]:
            allowed["community_id"] = open_roads
        generation = self._client.generate(
            ADVERSARY_SYSTEM.format(sources=source_pack()), "\n\n".join(lines), Attack, allowed
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
    for community in _towns(world, scenario):
        people = _affected_in(world, community)
        road = "road CLOSED" if community.id in scenario.closed_communities else "road open"
        towns.append(f"- id {community.id} ({community.name}): {people:.0f} affected, {road}")
    scope = world.community(scenario.scope) if scenario.scope else None
    return "\n".join(
        [
            *(
                [
                    f"The plan is for {scope.name} only: only its affected people count, "
                    "and any shelter may take them."
                ]
                if scope
                else []
            ),
            f"Affected people: {affected:.0f}. Budget: ${scenario.budget:,.0f}. "
            f"Transport: ${world.transport_cost_per_seat:,.0f} per seat.",
            "Shelters (refer to them by id):",
            *rows,
            *(["Communities (refer to them by id):", *towns] if towns else []),
        ]
    )


def _check(
    draft: Plan,
    result: SimulationResult,
    scenario: Scenario,
    world: World,
    label: str = "your draft",
) -> str:
    check = (
        f"Simulation check of {label} ({_actions(draft, world)}): "
        f"cost ${result.cost:,.0f}, shelters {result.people_sheltered:.0f} of "
        f"{result.people_affected:.0f} affected people "
        f"(you claimed ${draft.claims.cost:,.0f} and {draft.claims.people_sheltered:.0f}). "
        f"Cost of each action: {_cost_breakdown(draft, world)}; total ${result.cost:,.0f}. "
        "Your final claims.cost must be the total for your final actions."
    )
    if result.cost > scenario.budget:
        over = result.cost - scenario.budget
        return (
            f"{check} The plan is OVER BUDGET by ${over:,.0f}. "
            f"Your final plan must cost at most ${scenario.budget:,.0f}. "
            f"Ways to cut at least ${over:,.0f}: {_cuts(draft, world, over)}."
        )
    return f"{check} Keep the plan or improve it."


def _cuts(plan: Plan, world: World, over: float) -> str:
    """Concrete edits that would bring the plan back within budget, cheapest first."""
    options: list[str] = []
    for action in plan.actions:
        if isinstance(action, AllocateBudget) and action.amount - over >= 1_000:
            options.append(f"lower the reserve to ${action.amount - over:,.0f}")
        elif isinstance(action, AllocateBudget):
            options.append(f"drop the ${action.amount:,.0f} reserve")
        elif isinstance(action, StageTransport):
            seats = math.ceil(over / world.transport_cost_per_seat)
            if seats < action.seats:
                options.append(
                    f"stage {action.seats - seats} instead of {action.seats} seats for "
                    f"{action.community_id}"
                )
        elif isinstance(action, OpenShelter):
            shelter = world.shelter(action.shelter_id)
            if shelter and shelter.cost >= over:
                options.append(f"drop {shelter.id} (${shelter.cost:,.0f})")
    return "; or ".join(options[:4]) or "drop actions until the total fits"


def _cost_breakdown(plan: Plan, world: World) -> str:
    return "; ".join(
        f"{describe_action(a, world)} ${action_cost(world, a):,.0f}" for a in plan.actions
    )


def _towns(world: World, scenario: Scenario) -> list[Community]:
    """The communities the plan is for: the scenario's town, or all of them."""
    if scenario.scope is not None and (town := world.community(scenario.scope)):
        return [town]
    return list(world.communities)


def _affected_communities(world: World, scenario: Scenario) -> list[str]:
    return [c.id for c in _towns(world, scenario) if _affected_in(world, c) > 0]


def _affected_in(world: World, community: Community) -> float:
    cells = community.mask(world.grid.shape) & world.hazard.flooded
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
            line += f". Red team test: {describe_attack(round_.attack, world)}"
            if round_.attacked:
                line += f"; the plan then shelters {round_.attacked.people_sheltered:.0f}"
        lines.append(line + ".")
    return "\n".join(lines)


def _single_shelter_plan(shelter_id: str | None) -> Plan:
    """A plan opening one shelter, or none, for asking the Simulation what it achieves."""
    actions = [{"type": "open_shelter", "shelter_id": shelter_id}] if shelter_id else []
    return Plan.model_validate({"actions": actions, "claims": {"cost": 0, "people_sheltered": 0}})
