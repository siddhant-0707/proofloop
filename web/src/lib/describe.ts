// Plain-language descriptions of actions, attacks and conditions; mirrors loop/describe.py.

import type { Action, Attack, Scenario } from "@/lib/api";

export type PlaceName = (id: string) => string;

const dollars = (n: number) => `$${Math.round(n).toLocaleString()}`;

export function describeAction(action: Action, name: PlaceName): string {
  switch (action.type) {
    case "open_shelter":
      return `open ${name(action.shelter_id)}`;
    case "stage_transport":
      return `stage ${action.seats.toLocaleString()} transport seats for ${name(action.community_id)}`;
    case "allocate_budget":
      return `hold ${dollars(action.amount)} back as a contingency reserve`;
  }
}

export function describeAttack(attack: Attack, name: PlaceName): string {
  switch (attack.type) {
    case "shelter_offline":
      return `${name(attack.shelter_id)} goes offline`;
    case "road_closed":
      return `the road into ${name(attack.community_id)} closes`;
    case "budget_cut":
      return `the budget is cut by ${attack.percent}%`;
  }
}

/** Damage so far: offline shelters and closed roads, or "no damage yet". */
export function describeDamage(scenario: Scenario, name: PlaceName): string {
  const damage = [
    ...scenario.offline_shelters.map((id) => `${name(id)} offline`),
    ...scenario.closed_communities.map((id) => `road into ${name(id)} closed`),
  ];
  return damage.length ? damage.join("; ") : "no damage yet";
}

export function describePlan(actions: Action[], name: PlaceName): string {
  return actions.length ? actions.map((a) => describeAction(a, name)).join("; ") : "do nothing";
}
