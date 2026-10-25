// Turns run data into beats: what the map shows, one moment of the story at a time.

import type { Action, Round } from "@/lib/api";
import { describeAction, type PlaceName } from "@/lib/describe";
import { dollars, join, people } from "@/lib/format";

export type ShelterState = "open";

/** People heading from a town to a shelter; `carried` of them ride staged transport. */
export type Arc = { from: string; to: string; people: number; carried: number };

/** The headline counter; `reserve` is held back on top of `budgetUsed`, not spent. */
export type Figures = {
  atRisk: number;
  sheltered: number;
  budgetUsed: number;
  budget: number;
  reserve: number;
};

export type Beat = {
  /** "note": a caption with nothing to draw, such as a round without a plan. */
  kind: "plan" | "verdict" | "note";
  /** The round it belongs to, from 1. */
  round: number;
  caption: string;
  shelters: Record<string, ShelterState>;
  arcs: Arc[];
  figures: Figures | null;
  /** On a verdict beat: whether the plan's claims held, and why not. */
  verdict?: { passed: boolean; reason: string };
};

// Fewer people than this round to nobody.
const MIN_PEOPLE = 0.5;

/** One streamed Round as beats: the Planner's plan, then the Verifier's verdict. */
export function roundBeats(round: Round, name: PlaceName): Beat[] {
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
          .map((s) => ({ from, to: s.shelter_id, people: s.people, carried: s.carried })),
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
    figures: {
      atRisk: result.people_affected,
      sheltered: result.people_sheltered,
      budgetUsed: result.cost,
      budget: round.scenario.budget,
      reserve: plan.actions.reduce((sum, a) => sum + (a.type === "allocate_budget" ? a.amount : 0), 0),
    },
  };

  const failed = verdict.checks.find((c) => !c.passed);
  return [
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
}

/** "open A and B, stage 40 transport seats for C": shelters opened read as one phrase. */
function describeActions(actions: Action[], name: PlaceName): string {
  const opened = actions.flatMap((a) => (a.type === "open_shelter" ? [name(a.shelter_id)] : []));
  const others = actions.filter((a) => a.type !== "open_shelter").map((a) => describeAction(a, name));
  const parts = [...(opened.length ? [`open ${join(opened)}`] : []), ...others];
  return parts.length ? parts.join(", ") : "do nothing";
}
