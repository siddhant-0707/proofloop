import { describe, expect, it } from "vitest";

import type { Check, NeighborhoodBriefing, Round } from "@/lib/api";
import { roundBeats } from "@/lib/storyboard";

const NAMES: Record<string, string> = {
  "ruth-raines-ms": "Ruth Raines Middle School",
  "taylor-county-hs": "Taylor County High School",
  perry: "Perry",
  "cross-city": "Cross City",
  steinhatchee: "Steinhatchee",
};
const name = (id: string) => NAMES[id] ?? id;

function neighborhood(
  community_id: string | null,
  shelters: [string, number, number?][],
): NeighborhoodBriefing {
  const sheltered = shelters.reduce((sum, [, people]) => sum + people, 0);
  return {
    community_id,
    name: community_id ? name(community_id) : "Outside the towns",
    people_affected: sheltered,
    people_sheltered: sheltered,
    people_unreached: 0,
    shelters: shelters.map(([shelter_id, people, carried = 0]) => ({
      shelter_id,
      name: name(shelter_id),
      people,
      carried,
    })),
    transport_seats: 0,
    road_closed: false,
    steps: [],
  };
}

const passed = (n: string): Check => ({ name: n, passed: true, claimed: 1, actual: 1, reason: "" });

/** Round 1 of a real rule-based run over the whole area at $150,000, trimmed. */
function verifiedRound(): Round {
  const result = {
    people_affected: 959.68,
    people_sheltered: 959.51,
    people_unreached: 0.17,
    cost: 116_850,
    robustness: 0.9998,
    unfunded_actions: 0,
  };
  const scenario = { budget: 150_000, scope: null, offline_shelters: [], closed_communities: [] };
  return {
    index: 0,
    scenario,
    plan: {
      rationale: "The affordable set that shelters the most people.",
      actions: [
        { type: "open_shelter", shelter_id: "ruth-raines-ms" },
        { type: "open_shelter", shelter_id: "taylor-county-hs" },
      ],
      claims: { cost: 116_850, people_sheltered: 959.51 },
    },
    planner_error: null,
    planner_call: null,
    verdict: { passed: true, checks: ["cost", "people_sheltered", "budget"].map(passed) },
    result,
    attack: { rationale: "", type: "shelter_offline", shelter_id: "taylor-county-hs" },
    attacked: { ...result, people_sheltered: 453.13, people_unreached: 506.56, robustness: 0.47 },
    adversary_error: null,
    adversary_call: null,
    plan_from_round: null,
    report: {
      title: "Plan",
      scenario,
      result,
      sections: [],
      assignments: [],
      evidence: {},
      limitations: [],
      references: [],
      briefing: {
        conditions: [],
        limitations: [],
        neighborhoods: [
          neighborhood("perry", [["taylor-county-hs", 299.56]]),
          neighborhood("cross-city", [["ruth-raines-ms", 204.52]]),
          neighborhood("steinhatchee", [["ruth-raines-ms", 63.84, 40]]),
          neighborhood(null, [
            ["ruth-raines-ms", 168.2],
            ["taylor-county-hs", 201.3],
          ]),
        ],
      },
    },
  };
}

describe("a verified round", () => {
  it("first shows the Planner's shelters opening and people heading to them", () => {
    const [plan] = roundBeats(verifiedRound(), name);

    expect(plan.kind).toBe("plan");
    expect(plan.round).toBe(1);
    expect(plan.caption).toBe(
      "Round 1 · Planner: open Ruth Raines Middle School and Taylor County High School",
    );
    expect(plan.shelters).toEqual({
      "ruth-raines-ms": "open",
      "taylor-county-hs": "open",
    });
    expect(plan.arcs).toEqual([
      { from: "perry", to: "taylor-county-hs", people: 299.56, carried: 0 },
      { from: "cross-city", to: "ruth-raines-ms", people: 204.52, carried: 0 },
      { from: "steinhatchee", to: "ruth-raines-ms", people: 63.84, carried: 40 },
    ]);
    expect(plan.figures).toEqual({
      atRisk: 959.68,
      sheltered: 959.51,
      budgetUsed: 116_850,
      budget: 150_000,
      reserve: 0,
    });
  });

  it("names staged transport and the reserve held back", () => {
    const round = verifiedRound();
    round.plan!.actions.push(
      { type: "stage_transport", community_id: "steinhatchee", seats: 40 },
      { type: "allocate_budget", category: "contingency_reserve", amount: 5_000 },
    );

    const [plan] = roundBeats(round, name);

    expect(plan.caption).toBe(
      "Round 1 · Planner: open Ruth Raines Middle School and Taylor County High School, " +
        "stage 40 transport seats for Steinhatchee, hold $5,000 back as a contingency reserve",
    );
    expect(plan.figures?.reserve).toBe(5_000);
  });
});

describe("the Verifier's verdict", () => {
  it("follows the plan and says the claims check out", () => {
    const [plan, verdict] = roundBeats(verifiedRound(), name);

    expect(verdict.kind).toBe("verdict");
    expect(verdict.verdict).toEqual({ passed: true, reason: "Claims match the simulation" });
    expect(verdict.caption).toBe(
      "Round 1 · Verifier: verified, 960 of 960 people sheltered for $116,850",
    );
    expect(verdict.shelters).toEqual(plan.shelters);
    expect(verdict.arcs).toEqual(plan.arcs);
  });

  it("names the first failed check when it rejects the plan", () => {
    const round = verifiedRound();
    round.verdict = {
      passed: false,
      checks: [
        passed("cost"),
        {
          name: "people_sheltered",
          passed: false,
          claimed: 1_200,
          actual: 959.51,
          reason: "claimed 1,200 people sheltered; the simulation shelters 960",
        },
      ],
    };

    const verdict = roundBeats(round, name)[1];

    expect(verdict.verdict).toEqual({
      passed: false,
      reason: "claimed 1,200 people sheltered; the simulation shelters 960",
    });
    expect(verdict.caption).toBe(
      "Round 1 · Verifier: rejected, claimed 1,200 people sheltered; the simulation shelters 960",
    );
  });
});

describe("a round where the Planner failed", () => {
  it("says so in one caption when there is no plan to show", () => {
    const round = verifiedRound();
    Object.assign(round, {
      plan: null,
      verdict: null,
      result: null,
      attack: null,
      attacked: null,
      report: null,
      planner_error: "GenerationFailed: openrouter: invalid answer",
    });

    expect(roundBeats(round, name)).toEqual([
      {
        kind: "note",
        round: 1,
        caption: "Round 1 · The Planner could not produce a valid plan",
        shelters: {},
        arcs: [],
        figures: null,
      },
    ]);
  });

  it("says which earlier plan it tests again", () => {
    const round = { ...verifiedRound(), index: 1, plan_from_round: 0, planner_error: "invalid" };

    const [plan] = roundBeats(round, name);

    expect(plan.caption).toBe(
      "Round 2 · The Planner's answer was invalid; testing the round 1 plan again",
    );
    expect(plan.shelters).toEqual({ "ruth-raines-ms": "open", "taylor-county-hs": "open" });
  });
});
