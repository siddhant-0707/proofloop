"""ProofLoop: Planner proposes, Adversary attacks, code scores and verifies."""

import time
from collections.abc import Callable
from typing import Any

from proofloop.loop.agents import (
    Adversary,
    AgentReply,
    Planner,
    ScriptedAdversary,
    ScriptedPlanner,
)
from proofloop.loop.schemas import (
    AgentCall,
    Attack,
    Plan,
    Recommendation,
    Round,
    Scenario,
    Transcript,
)
from proofloop.loop.simulation import simulate
from proofloop.loop.verifier import verify
from proofloop.world import World

__all__ = [
    "Adversary",
    "AgentReply",
    "Attack",
    "Plan",
    "Planner",
    "Round",
    "Scenario",
    "ScriptedAdversary",
    "ScriptedPlanner",
    "Transcript",
    "run_proofloop",
    "simulate",
    "verify",
]

DEFAULT_ROUNDS = 3


def run_proofloop(
    world: World,
    scenario: Scenario,
    planner: Planner,
    adversary: Adversary,
    rounds: int = DEFAULT_ROUNDS,
    on_round: Callable[[Round], None] | None = None,
) -> Transcript:
    """Run `rounds` rounds of plan, verify, score and attack, then one final attack.

    `on_round` is called with each Round as soon as it completes, for streaming.
    """
    history: list[Round] = []
    current = scenario
    final_attack: Attack | None = None
    final_adversary_error: str | None = None
    final_adversary_call: AgentCall | None = None
    for index in range(rounds):
        plan, planner_error, planner_call = _ask(
            Plan.model_validate, planner.propose, world, current, history
        )
        if plan is None:
            best = _recommend(world, current, history)
            plan = best.plan if best else None

        verdict = verify(world, current, plan) if plan else None
        result = simulate(world, current, plan) if plan else None
        attack, adversary_error, adversary_call = _ask(
            lambda raw: _validate_attack(world, raw),
            adversary.attack,
            world,
            current,
            plan,
            result,
        )
        last = index == rounds - 1
        history.append(
            Round(
                index=index,
                scenario=current,
                plan=plan,
                planner_error=planner_error,
                planner_call=planner_call,
                verdict=verdict,
                result=result,
                attack=None if last else attack,
                adversary_error=None if last else adversary_error,
                adversary_call=None if last else adversary_call,
            )
        )
        if on_round:
            on_round(history[-1])
        if last:
            final_attack, final_adversary_error = attack, adversary_error
            final_adversary_call = adversary_call
        if attack is not None:
            current = current.with_offline(attack.shelter_id)

    return Transcript(
        base_scenario=scenario,
        rounds=history,
        final_attack=final_attack,
        final_adversary_error=final_adversary_error,
        final_adversary_call=final_adversary_call,
        final_scenario=current,
        recommendation=_recommend(world, current, history),
    )


def _ask[T](
    validate: Callable[[Any], T], call: Callable[..., Any], *args: Any
) -> tuple[T | None, str | None, AgentCall]:
    """Call an agent and validate its output; any failure becomes a recorded error.

    Agents may wrap their output in an AgentReply to say which model answered.
    """
    started = time.perf_counter()
    model = provider = None
    skipped: list[str] = []
    try:
        reply = call(*args)
        if isinstance(reply, AgentReply):
            model, provider, skipped = reply.model, reply.provider, reply.skipped
            reply = reply.output
        value, error = validate(reply), None
    except Exception as failure:  # noqa: BLE001 - agent failures must never crash a run
        value, error = None, f"{type(failure).__name__}: {failure}"
    seconds = time.perf_counter() - started
    return value, error, AgentCall(model=model, provider=provider, seconds=seconds, skipped=skipped)


def _validate_attack(world: World, raw: Any) -> Attack:
    attack = Attack.model_validate(raw)
    if world.shelter(attack.shelter_id) is None:
        raise ValueError(f"unknown shelter {attack.shelter_id}")
    return attack


def _recommend(world: World, final: Scenario, rounds: list[Round]) -> Recommendation | None:
    """The verified plan that shelters the most people once every attack has landed.

    Ties go to the earlier round, so a revision must strictly improve to replace it.
    """
    best: Recommendation | None = None
    for round_ in rounds:
        if round_.plan is None or round_.verdict is None or not round_.verdict.passed:
            continue
        result = simulate(world, final, round_.plan)
        if best is None or result.robustness > best.result.robustness:
            best = Recommendation(round_index=round_.index, plan=round_.plan, result=result)
    return best
