// Turns run data into beats: what the map shows, one moment of the story at a time.

import type {
  Action,
  Attack,
  Backup,
  Briefing,
  Recommendation,
  Round,
  SimulationResult,
  StressCase,
} from "@/lib/api";
import { describeAction, describeAttack, type PlaceName } from "@/lib/describe";
import { dollars, join, people, sentence } from "@/lib/format";

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
  /** "reroute": where people go once the attack hits. "backup": a stress case's backup plan
   * under its failures. "note": a caption with nothing to draw, such as a round without a plan. */
  kind: "plan" | "verdict" | "attack" | "reroute" | "backup" | "note";
  /** The round it belongs to, from 1; 0 outside a run (the final plan and its replays). */
  round: number;
  caption: string;
  shelters: Record<string, ShelterState>;
  arcs: Arc[];
  /** Towns whose road an attack closed. */
  cutTowns: string[];
  /** Town id -> people an attack keeps from the shelter they were heading to; on a reroute
   * beat, people who still reach no shelter. */
  unreached: Record<string, number>;
  figures: Figures | null;
  /** On a verdict beat: whether the plan's claims held, and why not. */
  verdict?: { passed: boolean; reason: string };
};

// Fewer people than this round to nobody.
const MIN_PEOPLE = 0.5;

/** One streamed Round as beats: the Planner's plan, the Verifier's verdict, then the
 * Adversary's attack and where people go under it (a re-plan's last round has none). */
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

  const planned = plannedBeat(
    number,
    round.plan_from_round != null
      ? `${label} · The Planner's answer was invalid; testing the round ${round.plan_from_round + 1} plan again`
      : `${label} · Planner: ${describeActions(plan.actions, name)}`,
    plan.actions,
    result,
    round.scenario.budget,
    round.report?.briefing ?? null,
  );

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
    const { attack, attacked } = round;
    const struck = attackBeat(
      planned,
      plan.actions,
      [attack],
      attacked,
      places,
      `${label} · Adversary: ${describeAttack(attack, name)}, ${sheltered(attacked)}`,
    );
    beats.push(struck);
    if (round.attacked_briefing) {
      beats.push(
        rerouteBeat(struck, round.attacked_briefing, `${label} · People reroute: ${reached(attacked)}`),
      );
    }
  }
  return beats;
}

/** The final plan as planned: drawn beside the report, and where a replay resets to. */
export function finalPlanBeat(rec: Recommendation, budget: number, name: PlaceName): Beat {
  return plannedBeat(
    0,
    `The plan: ${describeActions(rec.plan.actions, name)}, ${sheltered(rec.result)}`,
    rec.plan.actions,
    rec.result,
    budget,
    rec.report?.briefing ?? null,
  );
}

/** A stress case replayed on the final plan: its failures strike (all at once for a pair),
 * people reroute, then its backup plan, if it has one, takes over under the same failures. */
export function stressBeats(
  stress: StressCase,
  rec: Recommendation,
  budget: number,
  places: StoryPlaces,
): Beat[] {
  const { name } = places;
  const struck = attackBeat(
    finalPlanBeat(rec, budget, name),
    rec.plan.actions,
    stress.attacks,
    stress.result,
    places,
    `${sentence(join(stress.attacks.map((a) => describeAttack(a, name))))}, ${sheltered(stress.result)}`,
  );
  const beats = [struck];
  if (stress.briefing) {
    beats.push(rerouteBeat(struck, stress.briefing, `People reroute: ${reached(stress.result)}`));
  }
  if (stress.backup?.briefing) {
    beats.push(backupBeat(struck, stress.backup, stress.backup.briefing, stress.result, name));
  }
  return beats;
}

function plannedBeat(
  round: number,
  caption: string,
  actions: Action[],
  result: SimulationResult,
  budget: number,
  briefing: Briefing | null,
): Beat {
  const shelters: Record<string, ShelterState> = {};
  for (const action of actions) {
    if (action.type === "open_shelter") shelters[action.shelter_id] = "open";
  }
  return {
    kind: "plan",
    round,
    caption,
    shelters,
    arcs: briefing ? briefingArcs(briefing) : [],
    cutTowns: [],
    unreached: {},
    figures: {
      atRisk: result.people_affected,
      sheltered: result.people_sheltered,
      budgetUsed: result.cost,
      budget,
      reserve: reserve(actions),
    },
  };
}

/** Town -> shelter arcs from a field briefing. People flooded outside every town have no
 * single place to draw an arc from. */
function briefingArcs(briefing: Briefing): Arc[] {
  return briefing.neighborhoods.flatMap(({ community_id: from, shelters }) =>
    from == null
      ? []
      : shelters
          .filter((s) => s.people >= MIN_PEOPLE)
          .map((s) => ({ from, to: s.shelter_id, people: s.people, carried: s.carried, broken: false })),
  );
}

/** Town id -> people who reach no shelter, from a field briefing. */
function briefingUnreached(briefing: Briefing): Record<string, number> {
  const unreached: Record<string, number> = {};
  for (const { community_id: town, people_unreached: lost } of briefing.neighborhoods) {
    if (town != null && lost >= MIN_PEOPLE) unreached[town] = lost;
  }
  return unreached;
}

/** The attack beat redrawn with people sent to the shelters still open to them. */
function rerouteBeat(attackBeat: Beat, briefing: Briefing, caption: string): Beat {
  return {
    ...attackBeat,
    kind: "reroute",
    caption,
    arcs: briefingArcs(briefing),
    unreached: briefingUnreached(briefing),
  };
}

/** The backup plan under the attack beat's failures: the shelters it opens instead, and
 * where people go. */
function backupBeat(
  attackBeat: Beat,
  backup: Backup,
  briefing: Briefing,
  before: SimulationResult,
  name: PlaceName,
): Beat {
  const shelters: Record<string, ShelterState> = {};
  for (const [id, state] of Object.entries(attackBeat.shelters)) {
    if (state === "offline") shelters[id] = state;
  }
  for (const action of backup.actions) {
    if (action.type === "open_shelter") shelters[action.shelter_id] = "open";
  }
  for (const action of unfundedActions(backup.actions, backup.result.unfunded_actions)) {
    if (action.type === "open_shelter") shelters[action.shelter_id] = "unfunded";
  }
  return {
    ...attackBeat,
    kind: "backup",
    caption: `Backup plan: ${describeActions(backup.actions, name)}, ${sheltered(backup.result)}`,
    shelters,
    arcs: briefingArcs(briefing),
    unreached: briefingUnreached(briefing),
    figures: attackBeat.figures && {
      ...attackBeat.figures,
      sheltered: backup.result.people_sheltered,
      shelteredBefore: before.people_sheltered,
      budgetUsed: backup.result.cost,
      reserve: reserve(backup.actions),
    },
  };
}

/** "453 of 960 people sheltered". */
function sheltered(result: SimulationResult): string {
  return `${people(result.people_sheltered)} of ${people(result.people_affected)} people sheltered`;
}

/** "453 of 960 still reach a shelter". */
function reached(result: SimulationResult): string {
  return `${people(result.people_sheltered)} of ${people(result.people_affected)} still reach a shelter`;
}

function reserve(actions: Action[]): number {
  return actions.reduce((sum, a) => sum + (a.type === "allocate_budget" ? a.amount : 0), 0);
}

/** The plan with failures applied: what they take out, and who can no longer get through. */
function attackBeat(
  planned: Beat,
  actions: Action[],
  attacks: Attack[],
  attacked: SimulationResult,
  places: StoryPlaces,
  caption: string,
): Beat {
  const unfunded = unfundedActions(actions, attacked.unfunded_actions);
  const shelters = { ...planned.shelters };
  for (const attack of attacks) {
    if (attack.type === "shelter_offline") shelters[attack.shelter_id] = "offline";
  }
  for (const action of unfunded) {
    if (action.type === "open_shelter") shelters[action.shelter_id] = "unfunded";
  }
  const cutTowns = attacks.flatMap((a) => (a.type === "road_closed" ? [a.community_id] : []));
  const budget = attacks.reduce(
    (left, a) => (a.type === "budget_cut" ? left * (1 - a.percent / 100) : left),
    planned.figures?.budget ?? 0,
  );
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
    caption,
    shelters,
    arcs,
    cutTowns,
    unreached,
    figures: planned.figures && {
      ...planned.figures,
      sheltered: attacked.people_sheltered,
      shelteredBefore: planned.figures.sheltered,
      budget,
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
