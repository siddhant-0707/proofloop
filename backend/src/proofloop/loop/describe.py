"""Plain-language descriptions of actions and attacks, for agent prompts and summaries."""

from proofloop.loop.schemas import (
    Action,
    AllocateBudget,
    Attack,
    BudgetCut,
    OpenShelter,
    RoadClosed,
    Scenario,
    ShelterOffline,
    StageTransport,
    TargetOutreach,
    UnwarnedOutsideZone,
)
from proofloop.world import World


def describe_action(action: Action, world: World) -> str:
    if isinstance(action, OpenShelter):
        return f"open {_shelter_name(action.shelter_id, world)}"
    if isinstance(action, StageTransport):
        town = _community_name(action.community_id, world)
        return f"stage {action.seats} transport seats for {town}"
    if isinstance(action, TargetOutreach):
        return f"run outreach in {_community_name(action.community_id, world)}"
    assert isinstance(action, AllocateBudget)
    return f"hold ${action.amount:,.0f} back as a contingency reserve"


def describe_attack(attack: Attack, world: World) -> str:
    if isinstance(attack, ShelterOffline):
        return f"{_shelter_name(attack.shelter_id, world)} goes offline"
    if isinstance(attack, RoadClosed):
        return f"the road into {_community_name(attack.community_id, world)} closes"
    if isinstance(attack, BudgetCut):
        return f"the budget is cut by {attack.percent:g}%"
    assert isinstance(attack, UnwarnedOutsideZone)
    return "people flooded outside FEMA flood zones think they are safe and stay home"


def describe_damage(scenario: Scenario, world: World) -> str:
    """Attacks already in effect, or an empty string."""
    damage = [f"{_shelter_name(s, world)} offline" for s in sorted(scenario.offline_shelters)]
    damage += [
        f"road into {_community_name(c, world)} closed" for c in sorted(scenario.closed_communities)
    ]
    if scenario.unwarned_outside_zones:
        damage.append("people outside FEMA flood zones unwarned")
    return "; ".join(damage)


def _shelter_name(shelter_id: str, world: World) -> str:
    shelter = world.shelter(shelter_id)
    return shelter.name if shelter else shelter_id


def _community_name(community_id: str, world: World) -> str:
    community = world.community(community_id)
    return community.name if community else community_id
