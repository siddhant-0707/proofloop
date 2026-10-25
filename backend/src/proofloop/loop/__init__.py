"""ProofLoop: Planner proposes, Adversary attacks, code scores and verifies."""

import time
from collections.abc import Callable
from functools import partial
from typing import Any

from proofloop.loop.agents import (
    Adversary,
    AgentReply,
    Planner,
    ScriptedAdversary,
    ScriptedPlanner,
)
from proofloop.loop.baseline import baseline_plan, full_cover_cost, with_backup
from proofloop.loop.briefing import brief
from proofloop.loop.report import write_report
from proofloop.loop.schemas import (
    ATTACK,
    AgentCall,
    Attack,
    Candidate,
    Plan,
    Recommendation,
    RoadClosed,
    Round,
    Scenario,
    ShelterOffline,
    StressTest,
    Transcript,
)
from proofloop.loop.simulation import simulate, trace
from proofloop.loop.stress import (
    apply_attack,
    stress_case,
    stress_test,
    typical,
    unique_attacks,
)
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
_MIN_PEOPLE = 0.5
# Backup plans are built for every single failure and this many of the worst pairs.
_PAIRS_WITH_BACKUP = 5


def run_proofloop(
    world: World,
    scenario: Scenario,
    planner: Planner,
    adversary: Adversary,
    rounds: int = DEFAULT_ROUNDS,
    on_round: Callable[[Round], None] | None = None,
    final_attack: bool = True,
) -> Transcript:
    """Run `rounds` rounds: the Planner plans, code verifies and scores the plan, and the
    Adversary tests it with one failure.

    Every plan is made, verified and scored for `scenario`, the conditions the user set.
    The Adversary's failures never pile up: each tests one plan, and later rounds see
    them so the Planner can hedge. A plan is rejected only for its own mistakes (false
    claims, over budget, unknown or offline places), never because a failure hurts it.

    `on_round` is called with each Round as soon as it completes, for streaming.
    With `final_attack=False` (a quick re-plan) the Adversary skips the last round's plan.
    """
    history: list[Round] = []
    for index in range(rounds):
        last = index == rounds - 1
        plan, planner_error, planner_call = _ask(
            Plan.model_validate, planner.propose, world, scenario, history
        )
        plan_from_round = None
        best = _best(_candidates(world, scenario, history)) if plan is None else None
        if best is not None and best.round_index is not None:
            plan, plan_from_round = history[best.round_index].plan, best.round_index

        verdict = verify(world, scenario, plan) if plan else None
        result = simulate(world, scenario, plan) if plan else None
        attack, adversary_error, adversary_call = (
            _ask(
                partial(_validate_attack, world, scenario),
                adversary.attack,
                world,
                scenario,
                plan,
                result,
            )
            if final_attack or not last
            else (None, None, None)
        )
        hit = apply_attack(scenario, attack) if plan and attack else None
        history.append(
            Round(
                index=index,
                scenario=scenario,
                plan=plan,
                planner_error=planner_error,
                planner_call=planner_call,
                plan_from_round=plan_from_round,
                verdict=verdict,
                result=result,
                attack=attack,
                attacked=simulate(world, hit, plan) if plan and hit else None,
                attacked_briefing=(
                    brief(world, hit, trace(world, hit, plan)) if plan and hit else None
                ),
                adversary_error=adversary_error,
                adversary_call=adversary_call,
                report=write_report(world, scenario, plan, scenario) if plan else None,
            )
        )
        if on_round:
            on_round(history[-1])

    return Transcript(
        base_scenario=scenario,
        rounds=history,
        recommendation=_recommend(world, scenario, history),
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


def _validate_attack(world: World, scenario: Scenario, raw: Any) -> Attack:
    """Parse an attack; one on an unknown place, or one already in effect, is invalid."""
    attack = ATTACK.validate_python(raw)
    if isinstance(attack, ShelterOffline):
        if world.shelter(attack.shelter_id) is None:
            raise ValueError(f"unknown shelter {attack.shelter_id}")
        if attack.shelter_id in scenario.offline_shelters:
            raise ValueError(f"shelter {attack.shelter_id} is already offline")
    if isinstance(attack, RoadClosed):
        if world.community(attack.community_id) is None:
            raise ValueError(f"unknown community {attack.community_id}")
        if attack.community_id in scenario.closed_communities:
            raise ValueError(f"the road into {attack.community_id} is already closed")
        if scenario.scope is not None and attack.community_id != scenario.scope:
            raise ValueError(f"{attack.community_id} is outside the plan's scope")
    return attack


def _recommend(world: World, base: Scenario, rounds: list[Round]) -> Recommendation:
    """The best of the verified plans and the code-built baseline, with its report, its
    every-case stress test with backup plans, every failure the Adversary found at once,
    and every candidate it was chosen from.

    The baseline always competes, so the final plan never shelters fewer people than
    the best affordable set of shelters; on a tie the Planner's plan is kept."""
    found = unique_attacks([r.attack for r in rounds if r.attack])
    baseline = baseline_plan(world, base, found)
    candidates = [
        *_candidates(world, base, rounds),
        Candidate(
            round_index=None,
            result=simulate(world, base, baseline),
            typical=typical(world, base, baseline),
        ),
    ]
    best = _best(candidates)
    assert best is not None
    round_index = best.round_index
    plan = baseline if round_index is None else rounds[round_index].plan
    assert plan is not None
    result = simulate(world, base, plan)
    combined = stress_case(world, base, plan, found) if found else None
    return Recommendation(
        round_index=round_index,
        plan=plan,
        result=result,
        full_cover_cost=(
            full_cover_cost(world, base) if result.people_unreached >= _MIN_PEOPLE else None
        ),
        report=write_report(world, base, plan, base),
        stress=_with_backups(world, base, stress_test(world, base, plan)),
        combined=with_backup(world, base, combined) if combined else None,
        candidates=candidates,
    )


def _with_backups(world: World, base: Scenario, stress: StressTest) -> StressTest:
    pairs = 0
    cases = []
    for case in stress.cases:  # worst first
        if len(case.attacks) == 1 or pairs < _PAIRS_WITH_BACKUP:
            pairs += len(case.attacks) > 1
            case = with_backup(world, base, case)
        cases.append(case)
    return StressTest(cases=cases)


def _candidates(world: World, base: Scenario, rounds: list[Round]) -> list[Candidate]:
    """Each verified plan with its figures. A round re-testing an earlier plan adds nothing."""
    return [
        Candidate(round_index=r.index, result=r.result, typical=typical(world, base, r.plan))
        for r in rounds
        if r.plan is not None
        and r.plan_from_round is None
        and r.result is not None
        and r.verdict is not None
        and r.verdict.passed
    ]


def _best(candidates: list[Candidate]) -> Candidate | None:
    """The candidate that shelters the most people as planned; among those, the one that
    shelters the most on average under single failures; then the cheaper one; then the
    earlier one, so a later candidate (the baseline comes last) must strictly improve."""
    best: Candidate | None = None
    for candidate in candidates:
        if best is None or _rank(candidate) > _rank(best):
            best = candidate
    return best


def _rank(candidate: Candidate) -> tuple[float, float, float]:
    return (
        round(candidate.result.robustness, 9),
        round(candidate.typical, 9),
        -candidate.result.cost,
    )
