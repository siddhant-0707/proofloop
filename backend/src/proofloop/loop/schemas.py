"""Plan, Attack, Scenario and Transcript: the Loop's contract with agents and the web app."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Scenario(_Model):
    budget: float = Field(ge=0)
    offline_shelters: frozenset[str] = frozenset()

    def with_offline(self, shelter_id: str) -> "Scenario":
        return self.model_copy(update={"offline_shelters": self.offline_shelters | {shelter_id}})


class OpenShelter(_Model):
    type: Literal["open_shelter"] = "open_shelter"
    shelter_id: str


Action = OpenShelter


class Claims(_Model):
    cost: float
    people_sheltered: float


class Plan(_Model):
    # Rationale first, so a model explains itself before committing to actions and numbers.
    rationale: str = Field(default="", max_length=600)
    actions: list[Action]
    claims: Claims

    @property
    def shelter_ids(self) -> list[str]:
        """Shelters the plan opens, in plan order, without repeats."""
        return list(dict.fromkeys(action.shelter_id for action in self.actions))


class ShelterOffline(_Model):
    type: Literal["shelter_offline"] = "shelter_offline"
    shelter_id: str


Attack = ShelterOffline


class SimulationResult(_Model):
    people_affected: float
    people_sheltered: float
    people_unreached: float
    cost: float
    robustness: float


class Check(_Model):
    name: str
    passed: bool
    claimed: float | None = None
    actual: float | None = None
    reason: str = ""


class Verdict(_Model):
    passed: bool
    checks: list[Check]


class AgentCall(_Model):
    """Which model answered an agent call and how long it took (no model for rule-based agents)."""

    model: str | None = None
    provider: str | None = None
    seconds: float
    skipped: list[str] = []


class Round(_Model):
    index: int
    scenario: Scenario
    plan: Plan | None = None
    planner_error: str | None = None
    planner_call: AgentCall | None = None
    verdict: Verdict | None = None
    result: SimulationResult | None = None
    # The attack the next round has to answer; the last round's attack is the final attack.
    attack: Attack | None = None
    adversary_error: str | None = None
    adversary_call: AgentCall | None = None


class Recommendation(_Model):
    round_index: int
    plan: Plan
    result: SimulationResult  # scored under the final scenario, with every attack applied


class Transcript(_Model):
    base_scenario: Scenario
    rounds: list[Round]
    # The Adversary attacks once more after the last round; no plan answers it, and the
    # recommendation is the verified plan that best survives it on top of every earlier attack.
    final_attack: Attack | None = None
    final_adversary_error: str | None = None
    final_adversary_call: AgentCall | None = None
    final_scenario: Scenario
    recommendation: Recommendation | None = None
