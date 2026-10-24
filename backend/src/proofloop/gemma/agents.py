"""Gemma 4 Planner and Adversary.

Both see the same facts the Simulation uses: shelters, their capacity, cost and
availability, and how many affected people each can reach on its own. The
Planner also sees the Verifier's findings from earlier rounds.

The Planner has one check step: it drafts a plan, code simulates the draft, and
it writes its final plan and claims knowing what the draft achieved. The
Verifier still checks the final claims independently.
"""

import re
from collections.abc import Sequence

from proofloop.gemma.client import GemmaClient, Generation
from proofloop.gemma.sources import source_pack
from proofloop.loop.agents import AgentReply
from proofloop.loop.schemas import Attack, Plan, Round, Scenario, SimulationResult
from proofloop.loop.simulation import simulate
from proofloop.world import World

PLANNER_SYSTEM = """You are the Planner for a county emergency manager after a hurricane.
Choose which shelters to open so that as many affected people as possible are sheltered,
within the budget, and so that the plan still works if any single shelter goes offline.

Rules:
- Only open shelters from the list, and never one marked OFFLINE.
- Total cost must never exceed the budget, even if that means sheltering fewer people.
  A plan over budget is rejected outright.
- Claims are checked by exact simulation. claims.cost is the sum of the costs of the
  shelters you open. claims.people_sheltered must match the simulation within 1%:
  a shelter shelters at most its capacity, only people it can reach, and people
  reachable from several shelters are counted once.
- If an earlier round's claims were rejected, learn from the recomputed numbers.
- You get one simulation check of a draft before your final answer. If you change
  the shelters after the check, your claims must be your own best estimate.
- rationale: two or three sentences for the emergency manager, naming shelters by name
  (not id) and citing sources as [S1], [S2].

Sources:
{sources}"""

ADVERSARY_SYSTEM = """You are the Adversary, a red team testing a hurricane response plan.
Choose exactly one shelter to take offline (power loss, flooding, staff shortage) so
that the plan shelters as few people as possible. Prefer a shelter the plan relies on.
Only choose a shelter from the list.
rationale: one or two sentences on why this shelter could fail and why losing it hurts,
naming shelters by name (not id) and citing sources as [S1], [S2].

Sources:
{sources}"""


class GemmaPlanner:
    def __init__(self, client: GemmaClient):
        self._client = client

    def propose(self, world: World, scenario: Scenario, history: Sequence[Round]) -> AgentReply:
        system = PLANNER_SYSTEM.format(sources=source_pack())
        allowed = {"shelter_id": _available(world, scenario)}
        situation = "\n\n".join([_situation(world, scenario), _history(history)])

        draft = self._client.generate(system, f"{situation}\n\nDraft a plan.", Plan, allowed)
        checked = simulate(world, scenario, draft.value)
        final = self._client.generate(
            system,
            "\n\n".join(
                [situation, _check(draft.value, checked, scenario), "Give your final plan."]
            ),
            Plan,
            allowed,
        )
        return _reply(final, world, skipped=draft.skipped + final.skipped)


class GemmaAdversary:
    def __init__(self, client: GemmaClient):
        self._client = client

    def attack(
        self, world: World, scenario: Scenario, plan: Plan | None, result: SimulationResult | None
    ) -> AgentReply:
        lines = [_situation(world, scenario)]
        if plan and result:
            lines.append(
                f"The plan opens shelters {_shelters(plan)} and shelters "
                f"{result.people_sheltered:.0f} of {result.people_affected:.0f} affected people."
            )
        lines.append("Choose one shelter to take offline.")
        generation = self._client.generate(
            ADVERSARY_SYSTEM.format(sources=source_pack()),
            "\n\n".join(lines),
            Attack,
            allowed={"shelter_id": _available(world, scenario)},
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
    """Gemma sometimes cites shelters by id despite the prompt; show their names instead."""
    for shelter in sorted(world.shelters, key=lambda s: len(s.id), reverse=True):
        text = re.sub(rf"\b{re.escape(shelter.id)}\b", shelter.name, text)
    return text


def _shelters(plan: Plan) -> str:
    return ", ".join(plan.shelter_ids) or "none"


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
    return "\n".join(
        [
            f"Affected people: {affected:.0f}. Budget: ${scenario.budget:,.0f}.",
            "Shelters (refer to them by id):",
            *rows,
        ]
    )


def _check(draft: Plan, result: SimulationResult, scenario: Scenario) -> str:
    check = (
        f"Simulation check of your draft (opens {_shelters(draft)}): "
        f"cost ${result.cost:,.0f}, shelters {result.people_sheltered:.0f} of "
        f"{result.people_affected:.0f} affected people "
        f"(you claimed ${draft.claims.cost:,.0f} and {draft.claims.people_sheltered:.0f})."
    )
    if result.cost > scenario.budget:
        return (
            f"{check} The draft is OVER BUDGET by ${result.cost - scenario.budget:,.0f}. "
            f"Your final plan must cost at most ${scenario.budget:,.0f}; drop or swap shelters."
        )
    return f"{check} Keep the draft or improve it."


def _available(world: World, scenario: Scenario) -> list[str]:
    return [s.id for s in world.shelters if s.id not in scenario.offline_shelters]


def _history(history: Sequence[Round]) -> str:
    if not history:
        return "This is the first round."
    lines = ["Earlier rounds:"]
    for round_ in history:
        opened = _shelters(round_.plan) if round_.plan else "none (no valid plan)"
        line = f"- Round {round_.index + 1}: opened {opened}"
        if round_.result:
            line += f", sheltered {round_.result.people_sheltered:.0f}"
        if round_.verdict and not round_.verdict.passed:
            failed = "; ".join(c.reason or c.name for c in round_.verdict.checks if not c.passed)
            line += f". REJECTED by the Verifier: {failed}"
        if round_.attack:
            line += f". Then shelter {round_.attack.shelter_id} went offline"
        lines.append(line + ".")
    return "\n".join(lines)


def _single_shelter_plan(shelter_id: str | None) -> Plan:
    """A plan opening one shelter, or none, for asking the Simulation what it achieves."""
    actions = [{"type": "open_shelter", "shelter_id": shelter_id}] if shelter_id else []
    return Plan.model_validate({"actions": actions, "claims": {"cost": 0, "people_sheltered": 0}})
