"""Plan, Attack, Scenario and Transcript: the Loop's contract with agents and the web app."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Scenario(_Model):
    budget: float = Field(ge=0)
    offline_shelters: frozenset[str] = frozenset()
    # Communities whose land access is cut: their people cannot reach a shelter on their own.
    closed_communities: frozenset[str] = frozenset()
    # People flooded outside FEMA flood zones believe they are safe and stay home unless
    # outreach reaches their community.
    unwarned_outside_zones: bool = False

    def with_offline(self, shelter_id: str) -> "Scenario":
        return self.model_copy(update={"offline_shelters": self.offline_shelters | {shelter_id}})

    def with_closed(self, community_id: str) -> "Scenario":
        closed = self.closed_communities | {community_id}
        return self.model_copy(update={"closed_communities": closed})

    def with_unwarned(self) -> "Scenario":
        return self.model_copy(update={"unwarned_outside_zones": True})

    def with_budget_cut(self, percent: float) -> "Scenario":
        return self.model_copy(update={"budget": self.budget * (1 - percent / 100)})


class OpenShelter(_Model):
    type: Literal["open_shelter"] = "open_shelter"
    shelter_id: str


class StageTransport(_Model):
    """High-water vehicles that carry a community's people to open shelters with room."""

    type: Literal["stage_transport"] = "stage_transport"
    community_id: str
    seats: int = Field(ge=1, le=5_000)


class AllocateBudget(_Model):
    """Money held back; a later budget cut takes it before any action loses funding."""

    type: Literal["allocate_budget"] = "allocate_budget"
    category: Literal["contingency_reserve"] = "contingency_reserve"
    amount: float = Field(ge=1_000)


class TargetOutreach(_Model):
    """Warn a community's people flooded outside FEMA zones that they are at risk."""

    type: Literal["target_outreach"] = "target_outreach"
    community_id: str


Action = Annotated[
    OpenShelter | StageTransport | AllocateBudget | TargetOutreach, Field(discriminator="type")
]


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
        return list(dict.fromkeys(a.shelter_id for a in self.actions if isinstance(a, OpenShelter)))

    @property
    def community_ids(self) -> list[str]:
        """Communities the plan sends transport or outreach to, in plan order, without repeats."""
        return list(
            dict.fromkeys(
                a.community_id
                for a in self.actions
                if isinstance(a, StageTransport | TargetOutreach)
            )
        )


class ShelterOffline(_Model):
    # Rationale first, as in Plan: the Adversary says why before choosing.
    rationale: str = Field(default="", max_length=400)
    type: Literal["shelter_offline"] = "shelter_offline"
    shelter_id: str


class RoadClosed(_Model):
    rationale: str = Field(default="", max_length=400)
    type: Literal["road_closed"] = "road_closed"
    community_id: str


class BudgetCut(_Model):
    rationale: str = Field(default="", max_length=400)
    type: Literal["budget_cut"] = "budget_cut"
    percent: float = Field(ge=10, le=50)


class UnwarnedOutsideZone(_Model):
    """People flooded outside FEMA flood zones think they are safe and stay home."""

    rationale: str = Field(default="", max_length=400)
    type: Literal["unwarned_outside_zone"] = "unwarned_outside_zone"


Attack = Annotated[
    ShelterOffline | RoadClosed | BudgetCut | UnwarnedOutsideZone, Field(discriminator="type")
]
ATTACK = TypeAdapter(Attack)


class SimulationResult(_Model):
    people_affected: float
    people_sheltered: float
    people_unreached: float
    cost: float
    robustness: float
    # Actions left without money after a budget cut, in plan order.
    unfunded_actions: int = 0
    # Affected people outside FEMA flood zones (likely uninsured) whom the plan does not reach.
    people_unreached_outside_zones: float = 0.0


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
