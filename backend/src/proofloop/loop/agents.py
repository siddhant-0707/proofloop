"""Planner and Adversary interfaces, plus scripted implementations.

Agents return raw JSON-like mappings; the Loop validates them against the
Plan and Attack schemas so that malformed model output never crashes a run.
"""

from collections.abc import Sequence
from typing import Any, Protocol

from proofloop.loop.schemas import Plan, Round, Scenario, SimulationResult
from proofloop.world import World


class Planner(Protocol):
    def propose(self, world: World, scenario: Scenario, history: Sequence[Round]) -> Any: ...


class Adversary(Protocol):
    def attack(
        self, world: World, scenario: Scenario, plan: Plan | None, result: SimulationResult | None
    ) -> Any: ...


class _Script:
    """Pre-written responses returned in order, repeating the last one."""

    def __init__(self, responses: Sequence[Any]):
        if not responses:
            raise ValueError("a script needs at least one response")
        self._responses = list(responses)
        self._calls = 0

    def next(self) -> Any:
        response = self._responses[min(self._calls, len(self._responses) - 1)]
        self._calls += 1
        return response


class ScriptedPlanner:
    def __init__(self, responses: Sequence[Any]):
        self._script = _Script(responses)

    def propose(self, world: World, scenario: Scenario, history: Sequence[Round]) -> Any:
        return self._script.next()


class ScriptedAdversary:
    def __init__(self, responses: Sequence[Any]):
        self._script = _Script(responses)

    def attack(
        self, world: World, scenario: Scenario, plan: Plan | None, result: SimulationResult | None
    ) -> Any:
        return self._script.next()
