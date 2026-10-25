"""Field briefing: what staff do in each neighborhood, from a plan.

Neighborhoods are the World's communities; people flooded outside all of them get
one more line. Written by code templates from the same Trace the plan was scored
with, so every count in a step matches the plan's evidence.
"""

import numpy as np

from proofloop.loop.describe import describe_damage
from proofloop.loop.evidence import RADAR_LIMITATION, cell_size_m, money, people, sentence
from proofloop.loop.schemas import (
    Briefing,
    NeighborhoodBriefing,
    Scenario,
    ShelterAssignment,
    StageTransport,
)
from proofloop.loop.simulation import Trace
from proofloop.world import Community, World

OUTSIDE_TOWNS = "Outside any town"
# Neighborhoods with fewer affected people than this are left out of the briefing.
_MIN_PEOPLE = 0.5


def brief(world: World, scenario: Scenario, trace: Trace) -> Briefing:
    shape = world.grid.shape
    covered = np.zeros(shape, dtype=bool)
    neighborhoods: list[NeighborhoodBriefing] = []
    for community in world.communities:
        mask = community.mask(shape)
        covered |= mask
        neighborhoods.append(_neighborhood(world, scenario, trace, mask, community))
    neighborhoods.sort(key=lambda n: -n.people_affected)
    neighborhoods.append(_neighborhood(world, scenario, trace, ~covered, None))
    return Briefing(
        conditions=[f"Budget {money(scenario.budget)}", *_damage(scenario, world)],
        neighborhoods=[n for n in neighborhoods if n.people_affected >= _MIN_PEOPLE],
        limitations=_limitations(world),
    )


def _neighborhood(
    world: World, scenario: Scenario, trace: Trace, mask: np.ndarray, community: Community | None
) -> NeighborhoodBriefing:
    community_id = community.id if community else None
    affected = float(trace.affected[mask].sum())
    unreached = float(trace.unreached[mask].sum())
    shelters = []
    for shelter_id, walked in trace.walked.items():
        carried = sum(
            c.people
            for c in trace.carried
            if c.community_id == community_id and c.shelter_id == shelter_id
        )
        walk_in = float((walked.people * mask[walked.rows, walked.cols]).sum())
        if walk_in + carried >= _MIN_PEOPLE:
            shelter = world.shelter(shelter_id)
            shelters.append(
                ShelterAssignment(
                    shelter_id=shelter_id,
                    name=shelter.name if shelter else shelter_id,
                    people=walk_in + carried,
                    carried=carried,
                )
            )
    briefing = NeighborhoodBriefing(
        community_id=community_id,
        name=community.name if community else OUTSIDE_TOWNS,
        people_affected=affected,
        people_sheltered=affected - unreached,
        people_unreached=unreached,
        shelters=shelters,
        transport_seats=sum(
            a.seats
            for a in trace.funded
            if isinstance(a, StageTransport) and a.community_id == community_id
        ),
        road_closed=community_id in scenario.closed_communities,
        steps=[],
    )
    return briefing.model_copy(update={"steps": _steps(briefing)})


def _steps(n: NeighborhoodBriefing) -> list[str]:
    steps: list[str] = []
    if n.shelters:
        where = _join([f"{s.name} (about {people(s.people)})" for s in n.shelters])
        steps.append(f"Direct residents to {where}.")
    if n.transport_seats:
        carried = sum(s.carried for s in n.shelters)
        steps.append(
            f"Stage {n.transport_seats} transport seats at the town center and pick up the "
            f"households nearest it first, carrying about {_people(carried)}."
        )
    if n.road_closed:
        steps.append(
            "The road out is closed, so people cannot leave on their own: "
            + ("transport is their way out." if n.transport_seats else "plan rescues.")
        )
    if n.people_unreached >= _MIN_PEOPLE:
        steps.append(
            f"About {_people(n.people_unreached)} cannot reach an open shelter under these "
            "conditions: plan welfare checks and rescues."
        )
    else:
        steps.append("Everyone affected here can reach a shelter.")
    return steps


def _people(count: float) -> str:
    number = people(count)
    return f"{number} {'person' if number == '1' else 'people'}"


def _damage(scenario: Scenario, world: World) -> list[str]:
    damage = describe_damage(scenario, world)
    return [sentence(d) for d in damage.split("; ")] if damage else []


def _limitations(world: World) -> list[str]:
    limitations = [RADAR_LIMITATION]
    radii = {c.radius_cells for c in world.communities}
    if len(radii) == 1:
        radius_km = radii.pop() * cell_size_m(world) / 1000
        limitations.append(
            f"A neighborhood is everyone within {radius_km:.0f} km of a town center; affected "
            f'people farther out are grouped under "{OUTSIDE_TOWNS}".'
        )
    limitations += [
        "Counts are estimates from 2020 Census blocks spread over grid cells, not household "
        "addresses.",
        "Shelter assignments follow the simulation's nearest-first rule; real arrivals will "
        "differ.",
    ]
    return limitations


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
