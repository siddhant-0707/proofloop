"""Gemma 4 Planner and Adversary.

Both see the same facts the Simulation uses: shelters, their capacity, cost and
availability, and how many affected people each can reach on its own. The
Planner also sees the Verifier's findings from earlier rounds, so it can fix
claims it got wrong.
"""

from collections.abc import Sequence

from proofloop.gemma.client import GemmaClient
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
- Total cost must not exceed the budget.
- Claims are checked by exact simulation. claims.cost is the sum of the costs of the
  shelters you open. claims.people_sheltered must match the simulation within 1%:
  a shelter shelters at most its capacity, only people it can reach, and people
  reachable from several shelters are counted once.
- If an earlier round's claims were rejected, learn from the recomputed numbers.
- rationale: two or three sentences for the emergency manager, citing sources as [S1], [S2].

Sources:
{sources}"""

ADVERSARY_SYSTEM = """You are the Adversary, a red team testing a hurricane response plan.
Choose exactly one shelter to take offline (power loss, flooding, staff shortage) so
that the plan shelters as few people as possible. Prefer a shelter the plan relies on.
Only choose a shelter from the list."""


class GemmaPlanner:
    def __init__(self, client: GemmaClient):
        self._client = client

    def propose(self, world: World, scenario: Scenario, history: Sequence[Round]) -> AgentReply:
        prompt = "\n\n".join([_situation(world, scenario), _history(history), "Propose a plan."])
        generation = self._client.generate(
            PLANNER_SYSTEM.format(sources=source_pack()),
            prompt,
            Plan,
            allowed={"shelter_id": _available(world, scenario)},
        )
        return AgentReply(
            output=generation.value.model_dump(),
            model=generation.model,
            provider=generation.provider,
            skipped=generation.skipped,
        )


class GemmaAdversary:
    def __init__(self, client: GemmaClient):
        self._client = client

    def attack(
        self, world: World, scenario: Scenario, plan: Plan | None, result: SimulationResult | None
    ) -> AgentReply:
        lines = [_situation(world, scenario)]
        if plan and result:
            lines.append(
                f"The plan opens shelters {', '.join(plan.shelter_ids) or 'none'} and shelters "
                f"{result.people_sheltered:.0f} of {result.people_affected:.0f} affected people."
            )
        lines.append("Choose one shelter to take offline.")
        generation = self._client.generate(
            ADVERSARY_SYSTEM,
            "\n\n".join(lines),
            Attack,
            allowed={"shelter_id": _available(world, scenario)},
        )
        return AgentReply(
            output=generation.value.model_dump(),
            model=generation.model,
            provider=generation.provider,
            skipped=generation.skipped,
        )


def _situation(world: World, scenario: Scenario) -> str:
    affected = float(world.population[world.hazard.flooded].sum())
    rows = []
    for shelter in world.shelters:
        if shelter.id in scenario.offline_shelters:
            rows.append(f"- id {shelter.id} ({shelter.name}): OFFLINE")
            continue
        alone = simulate(world, scenario, _only(shelter.id)).people_sheltered
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


def _available(world: World, scenario: Scenario) -> list[str]:
    return [s.id for s in world.shelters if s.id not in scenario.offline_shelters]


def _history(history: Sequence[Round]) -> str:
    if not history:
        return "This is the first round."
    lines = ["Earlier rounds:"]
    for round_ in history:
        opened = ", ".join(round_.plan.shelter_ids) if round_.plan else "no plan"
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


def _only(shelter_id: str) -> Plan:
    return Plan.model_validate(
        {
            "actions": [{"type": "open_shelter", "shelter_id": shelter_id}],
            "claims": {"cost": 0, "people_sheltered": 0},
        }
    )
