"""Plan, Attack, Scenario and Transcript: the Loop's contract with agents and the web app."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Scenario(_Model):
    budget: float = Field(ge=0)
    # A community id to plan for that town's affected people only; None plans for the whole
    # area. Any shelter may still take them.
    scope: str | None = None
    offline_shelters: frozenset[str] = frozenset()
    # Communities whose land access is cut: their people cannot reach a shelter on their own.
    closed_communities: frozenset[str] = frozenset()

    def with_offline(self, shelter_id: str) -> "Scenario":
        return self.model_copy(update={"offline_shelters": self.offline_shelters | {shelter_id}})

    def with_closed(self, community_id: str) -> "Scenario":
        closed = self.closed_communities | {community_id}
        return self.model_copy(update={"closed_communities": closed})

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


Action = Annotated[OpenShelter | StageTransport | AllocateBudget, Field(discriminator="type")]


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
        """Communities the plan sends transport to, in plan order, without repeats."""
        return list(
            dict.fromkeys(a.community_id for a in self.actions if isinstance(a, StageTransport))
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


Attack = Annotated[ShelterOffline | RoadClosed | BudgetCut, Field(discriminator="type")]
ATTACK = TypeAdapter(Attack)


class SimulationResult(_Model):
    people_affected: float
    people_sheltered: float
    people_unreached: float
    cost: float
    robustness: float
    # Actions left without money after a budget cut, in plan order.
    unfunded_actions: int = 0


class SourceRef(_Model):
    id: str
    title: str
    origin: str


class Evidence(_Model):
    """Where one figure comes from: its sources, how code computes it, and what it assumes."""

    sources: list[SourceRef]
    formula: str
    # This plan's and scenario's numbers that went into the figure.
    inputs: list[str] = []
    assumptions: list[str]
    limitations: list[str]


class ShelterAssignment(_Model):
    shelter_id: str
    name: str
    people: float
    # Of `people`, how many staged transport carries there.
    carried: float = 0.0


class NeighborhoodBriefing(_Model):
    # None for the people flooded outside every community.
    community_id: str | None
    name: str
    people_affected: float
    people_sheltered: float
    people_unreached: float
    shelters: list[ShelterAssignment]
    transport_seats: int
    road_closed: bool
    steps: list[str]


class Briefing(_Model):
    """What staff do in each neighborhood under the report's conditions, from its plan."""

    conditions: list[str]
    neighborhoods: list[NeighborhoodBriefing]
    limitations: list[str]


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


class Assignment(_Model):
    """One work assignment of a plan, in the manner of an ICS 204 assignment list."""

    kind: Literal["shelter", "transport", "reserve"]
    title: str
    resource: str
    work: str
    people: float | None = None
    cost: float
    funded: bool


class ReportSection(_Model):
    title: str
    lines: list[str]


class PlanReport(_Model):
    """A plan written up as an operations plan, by code, under one set of conditions."""

    title: str
    scenario: Scenario
    result: SimulationResult
    # Situation, objectives, assumptions and concept of operations, in that order.
    sections: list[ReportSection]
    assignments: list[Assignment]
    briefing: Briefing
    # Evidence for each figure of `result`, plus "budget".
    evidence: dict[str, Evidence]
    limitations: list[str]
    references: list[SourceRef]


class Round(_Model):
    index: int
    # The conditions the plan is made, verified and scored for: the run's base scenario.
    scenario: Scenario
    plan: Plan | None = None
    planner_error: str | None = None
    planner_call: AgentCall | None = None
    # Set when the Planner's output was invalid and this round re-tests an earlier round's plan.
    plan_from_round: int | None = None
    verdict: Verdict | None = None
    result: SimulationResult | None = None
    # The Adversary's test of this plan: one failure on top of `scenario`. Failures never
    # pile up; later rounds see them so the Planner can hedge.
    attack: Attack | None = None
    # The plan's result with `attack` applied.
    attacked: SimulationResult | None = None
    # Where people go once `attack` hits: the field briefing for the plan under it.
    attacked_briefing: Briefing | None = None
    adversary_error: str | None = None
    adversary_call: AgentCall | None = None
    # The plan written up under `scenario`.
    report: PlanReport | None = None


class Backup(_Model):
    """What to do instead when a failure hits: a plan built by code for those conditions."""

    actions: list[Action]
    result: SimulationResult


class StressCase(_Model):
    attacks: list[Attack]
    result: SimulationResult
    # Set when a backup plan shelters more people under these failures than the plan does.
    backup: Backup | None = None


class StressTest(_Model):
    """The recommended plan under every single attack and every pair, on top of the base
    scenario, worst first."""

    cases: list[StressCase]


class Candidate(_Model):
    """A verified plan and the figures the recommendation is chosen by: first the share
    sheltered as planned, then `typical`."""

    # None for the code-built baseline plan, which every run includes.
    round_index: int | None
    result: SimulationResult  # as planned, under the base scenario
    # Average share sheltered over every single failure the stress test tries.
    typical: float


class Recommendation(_Model):
    # None when the code-built baseline plan shelters more than every verified plan (or
    # none passed verification).
    round_index: int | None
    plan: Plan
    result: SimulationResult  # as planned, under the base scenario
    # When the plan leaves people unsheltered as planned: the cost of the cheapest set of
    # shelters that takes everyone, or None when no set of shelters can.
    full_cover_cost: float | None = None
    # The plan written up under the base scenario: the conditions it is planned for.
    report: PlanReport | None = None
    stress: StressTest | None = None
    # Every failure the Adversary found, all at once.
    combined: StressCase | None = None
    # Every verified round's plan, the recommended one included.
    candidates: list[Candidate] = []


class Transcript(_Model):
    base_scenario: Scenario
    rounds: list[Round]
    recommendation: Recommendation | None = None
