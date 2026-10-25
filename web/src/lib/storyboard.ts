// Turns run data into beats: what the map shows, one moment of the story at a time.

import type { Action, Attack, Round, SimulationResult } from "@/lib/api";
import { describeAction, describeAttack, type PlaceName } from "@/lib/describe";
import { dollars, join, people } from "@/lib/format";

/** Names for captions, and the shelters within each town's radius: a closed road does not
 * cut a town off from those. */
export type StoryPlaces = { name: PlaceName; sheltersIn: Record<string, string[]> };

/** "offline": an attack took the shelter out; "unfunded": a budget cut took its money. */
export type ShelterState = "open" | "offline" | "unfunded";

/** People heading from a town to a shelter; `carried` of them ride staged transport.
 * `broken` once an attack stops them getting there. */
export type Arc = { from: string; to: string; people: number; carried: number; broken: boolean };

/** The headline counter; `reserve` is held back on top of `budgetUsed`, not spent. */
export type Figures = {
  atRisk: number;
  sheltered: number;
  budgetUsed: number;
  budget: number;
  reserve: number;
  /** After an attack: sheltered as planned, before the failure. */
  shelteredBefore?: number;
};

export type Beat = {
  /** "note": a caption with nothing to draw, such as a round without a plan. */
  kind: "plan" | "verdict" | "attack" | "note";
  /** The round it belongs to, from 1. */
  round: number;
  caption: string;
  shelters: Record<string, ShelterState>;
  arcs: Arc[];
  /** Towns whose road an attack closed. */
  cutTowns: string[];
  /** Town id -> people an attack keeps from the shelter they were heading to. */
  unreached: Record<string, number>;
  figures: Figures | null;
  /** On a verdict beat: whether the plan's claims held, and why not. */
  verdict?: { passed: boolean; reason: string };
};

// Fewer people than this round to nobody.
const MIN_PEOPLE = 0.5;

/** One streamed Round as beats: the Planner's plan, the Verifier's verdict, then the
 * Adversary's attack (a re-plan's last round has none). */
export function roundBeats(round: Round, places: StoryPlaces): Beat[] {
  const { name } = places;
  const number = round.index + 1;
  const label = `Round ${number}`;
  const { plan, result, verdict } = round;
  if (!plan || !result || !verdict) {
    return [
      {
        kind: "note",
        round: number,
        caption: `${label} · The Planner could not produce a valid plan`,
        shelters: {},
        arcs: [],
        cutTowns: [],
        unreached: {},
        figures: null,
      },
    ];
  }

  const shelters: Record<string, ShelterState> = {};
  for (const action of plan.actions) {
    if (action.type === "open_shelter") shelters[action.shelter_id] = "open";
  }
  // People flooded outside every town have no single place to draw an arc from.
  const arcs = (round.report?.briefing.neighborhoods ?? []).flatMap(({ community_id: from, shelters }) =>
    from == null
      ? []
      : shelters
          .filter((s) => s.people >= MIN_PEOPLE)
          .map((s) => ({ from, to: s.shelter_id, people: s.people, carried: s.carried, broken: false })),
  );
  const planned: Beat = {
    kind: "plan",
    round: number,
    caption:
      round.plan_from_round != null
        ? `${label} · The Planner's answer was invalid; testing the round ${round.plan_from_round + 1} plan again`
        : `${label} · Planner: ${describeActions(plan.actions, name)}`,
    shelters,
    arcs,
    cutTowns: [],
    unreached: {},
    figures: {
      atRisk: result.people_affected,
      sheltered: result.people_sheltered,
      budgetUsed: result.cost,
      budget: round.scenario.budget,
      reserve: plan.actions.reduce((sum, a) => sum + (a.type === "allocate_budget" ? a.amount : 0), 0),
    },
  };

  const failed = verdict.checks.find((c) => !c.passed);
  const beats: Beat[] = [
    planned,
    {
      ...planned,
      kind: "verdict",
      caption: failed
        ? `${label} · Verifier: rejected, ${failed.reason}`
        : `${label} · Verifier: verified, ${people(result.people_sheltered)} of ${people(result.people_affected)} people sheltered for ${dollars(result.cost)}`,
      verdict: failed
        ? { passed: false, reason: failed.reason }
        : { passed: true, reason: "Claims match the simulation" },
    },
  ];
  if (round.attack && round.attacked) {
    beats.push(attackBeat(planned, plan.actions, round.attack, round.attacked, places));
  }
  return beats;
}

/** The plan with one failure applied: what it takes out, and who can no longer get through. */
function attackBeat(
  planned: Beat,
  actions: Action[],
  attack: Attack,
  attacked: SimulationResult,
  places: StoryPlaces,
): Beat {
  const unfunded = unfundedActions(actions, attacked.unfunded_actions);
  const shelters = { ...planned.shelters };
  if (attack.type === "shelter_offline") shelters[attack.shelter_id] = "offline";
  for (const action of unfunded) {
    if (action.type === "open_shelter") shelters[action.shelter_id] = "unfunded";
  }
  const cutTowns = attack.type === "road_closed" ? [attack.community_id] : [];
  const riders = fundedRiders(actions, unfunded);
  const unreached: Record<string, number> = {};
  const arcs = planned.arcs.map((arc) => {
    // Funded transport still fills spare beds in any open shelter, closed road or not, so an
    // attack stops the people who would have walked: to a shelter that closed or lost its
    // money, or out of a town cut off from a shelter outside it. Riders whose seats lost
    // their money are stopped too.
    const carried = arc.carried * riders(arc.from);
    const blocked =
      shelters[arc.to] !== "open" ||
      (cutTowns.includes(arc.from) && !(places.sheltersIn[arc.from] ?? []).includes(arc.to));
    const lost = (blocked ? arc.people : arc.carried) - carried;
    if (lost >= MIN_PEOPLE) unreached[arc.from] = (unreached[arc.from] ?? 0) + lost;
    return { ...arc, broken: lost >= MIN_PEOPLE };
  });
  return {
    ...planned,
    kind: "attack",
    caption: `Round ${planned.round} · Adversary: ${describeAttack(attack, places.name)}, ${people(attacked.people_sheltered)} of ${people(attacked.people_affected)} people sheltered`,
    shelters,
    arcs,
    cutTowns,
    unreached,
    figures: planned.figures && {
      ...planned.figures,
      sheltered: attacked.people_sheltered,
      shelteredBefore: planned.figures.sheltered,
      budget:
        attack.type === "budget_cut"
          ? planned.figures.budget * (1 - attack.percent / 100)
          : planned.figures.budget,
    },
  };
}

/** Town id -> the share of its staged transport seats still funded. */
function fundedRiders(actions: Action[], unfunded: Action[]): (town: string) => number {
  const seats = (list: Action[], town: string) =>
    list.reduce((n, a) => n + (a.type === "stage_transport" && a.community_id === town ? a.seats : 0), 0);
  return (town) => {
    const staged = seats(actions, town);
    return staged ? 1 - seats(unfunded, town) / staged : 1;
  };
}

/** The `count` actions that lose their money under a smaller budget: funding runs in plan
 * order, a shelter is paid for once and the reserve needs none (as the Simulation funds). */
function unfundedActions(actions: Action[], count: number): Action[] {
  const opened = new Set<string>();
  const billable = actions.filter((a) => {
    if (a.type === "allocate_budget") return false;
    if (a.type !== "open_shelter") return true;
    if (opened.has(a.shelter_id)) return false;
    opened.add(a.shelter_id);
    return true;
  });
  return count > 0 ? billable.slice(-count) : [];
}

/** "open A and B, stage 40 transport seats for C": shelters opened read as one phrase. */
function describeActions(actions: Action[], name: PlaceName): string {
  const opened = actions.flatMap((a) => (a.type === "open_shelter" ? [name(a.shelter_id)] : []));
  const others = actions.filter((a) => a.type !== "open_shelter").map((a) => describeAction(a, name));
  const parts = [...(opened.length ? [`open ${join(opened)}`] : []), ...others];
  return parts.length ? parts.join(", ") : "do nothing";
}
