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
const places = {
  name,
  sheltersIn: { perry: ["taylor-county-hs"], "cross-city": ["ruth-raines-ms"] },
};

function neighborhood(
  community_id: string | null,
  shelters: [string, number, number?][],
  unreached = 0,
): NeighborhoodBriefing {
  const sheltered = shelters.reduce((sum, [, people]) => sum + people, 0);
  return {
    community_id,
    name: community_id ? name(community_id) : "Outside the towns",
    people_affected: sheltered + unreached,
    people_sheltered: sheltered,
    people_unreached: unreached,
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
    attacked_briefing: null,
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
    const [plan] = roundBeats(verifiedRound(), places);

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
      { from: "perry", to: "taylor-county-hs", people: 299.56, carried: 0, broken: false },
      { from: "cross-city", to: "ruth-raines-ms", people: 204.52, carried: 0, broken: false },
      { from: "steinhatchee", to: "ruth-raines-ms", people: 63.84, carried: 40, broken: false },
    ]);
    expect(plan.cutTowns).toEqual([]);
    expect(plan.unreached).toEqual({});
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

    const [plan] = roundBeats(round, places);

    expect(plan.caption).toBe(
      "Round 1 · Planner: open Ruth Raines Middle School and Taylor County High School, " +
        "stage 40 transport seats for Steinhatchee, hold $5,000 back as a contingency reserve",
    );
    expect(plan.figures?.reserve).toBe(5_000);
  });
});

describe("the Verifier's verdict", () => {
  it("follows the plan and says the claims check out", () => {
    const [plan, verdict] = roundBeats(verifiedRound(), places);

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

    const verdict = roundBeats(round, places)[1];

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

    expect(roundBeats(round, places)).toEqual([
      {
        kind: "note",
        round: 1,
        caption: "Round 1 · The Planner could not produce a valid plan",
        shelters: {},
        arcs: [],
        cutTowns: [],
        unreached: {},
        figures: null,
      },
    ]);
  });

  it("says which earlier plan it tests again", () => {
    const round = { ...verifiedRound(), index: 1, plan_from_round: 0, planner_error: "invalid" };

    const [plan] = roundBeats(round, places);

    expect(plan.caption).toBe(
      "Round 2 · The Planner's answer was invalid; testing the round 1 plan again",
    );
    expect(plan.shelters).toEqual({ "ruth-raines-ms": "open", "taylor-county-hs": "open" });
  });
});

describe("the Adversary's attack", () => {
  it("strikes a shelter: it goes offline and the people heading there are no longer reached", () => {
    const [, , attack] = roundBeats(verifiedRound(), places);

    expect(attack.kind).toBe("attack");
    expect(attack.caption).toBe(
      "Round 1 · Adversary: Taylor County High School goes offline, 453 of 960 people sheltered",
    );
    expect(attack.shelters).toEqual({ "ruth-raines-ms": "open", "taylor-county-hs": "offline" });
    expect(attack.arcs.map((a) => [a.from, a.broken])).toEqual([
      ["perry", true],
      ["cross-city", false],
      ["steinhatchee", false],
    ]);
    expect(attack.unreached).toEqual({ perry: 299.56 });
    expect(attack.figures).toEqual({
      atRisk: 959.68,
      sheltered: 453.13,
      shelteredBefore: 959.51,
      budgetUsed: 116_850,
      budget: 150_000,
      reserve: 0,
    });
  });

  it("closes a road: the town is cut off from shelters outside it, but transport still runs", () => {
    const round = verifiedRound();
    round.attack = { rationale: "", type: "road_closed", community_id: "steinhatchee" };
    round.attacked = { ...round.result!, people_sheltered: 935.67, people_unreached: 24.01 };

    const attack = roundBeats(round, places)[2];

    expect(attack.caption).toBe(
      "Round 1 · Adversary: the road into Steinhatchee closes, 936 of 960 people sheltered",
    );
    expect(attack.cutTowns).toEqual(["steinhatchee"]);
    expect(attack.shelters).toEqual({ "ruth-raines-ms": "open", "taylor-county-hs": "open" });
    expect(attack.arcs.filter((a) => a.broken).map((a) => a.from)).toEqual(["steinhatchee"]);
    expect(attack.unreached).toEqual({ steinhatchee: 63.84 - 40 });
  });

  it("closes a road into a town with its own shelter: nobody there is cut off", () => {
    const round = verifiedRound();
    round.attack = { rationale: "", type: "road_closed", community_id: "perry" };

    const attack = roundBeats(round, places)[2];

    expect(attack.cutTowns).toEqual(["perry"]);
    expect(attack.arcs.some((a) => a.broken)).toBe(false);
    expect(attack.unreached).toEqual({});
  });

  it("cuts the budget: the last actions lose their money and their shelters go dark", () => {
    const round = verifiedRound();
    round.plan!.actions.push({ type: "allocate_budget", category: "contingency_reserve", amount: 5_000 });
    round.attack = { rationale: "", type: "budget_cut", percent: 25 };
    round.attacked = { ...round.result!, people_sheltered: 453.13, unfunded_actions: 1 };

    const attack = roundBeats(round, places)[2];

    expect(attack.caption).toBe(
      "Round 1 · Adversary: the budget is cut by 25%, 453 of 960 people sheltered",
    );
    expect(attack.shelters).toEqual({ "ruth-raines-ms": "open", "taylor-county-hs": "unfunded" });
    expect(attack.unreached).toEqual({ perry: 299.56 });
    expect(attack.figures).toMatchObject({ budget: 112_500, sheltered: 453.13, shelteredBefore: 959.51 });
  });

  it("is left out of a re-plan's last round, which has no attack", () => {
    const round = { ...verifiedRound(), attack: null, attacked: null, attacked_briefing: null };

    expect(roundBeats(round, places).map((b) => b.kind)).toEqual(["plan", "verdict"]);
  });

  it("lets funded transport riders through: buses fill spare beds in any open shelter", () => {
    const round = verifiedRound();
    round.plan!.actions.push({ type: "stage_transport", community_id: "steinhatchee", seats: 40 });
    round.attack = { rationale: "", type: "shelter_offline", shelter_id: "ruth-raines-ms" };

    const attack = roundBeats(round, places)[2];

    expect(attack.unreached).toEqual({ "cross-city": 204.52, steinhatchee: 63.84 - 40 });
  });

  it("loses only the riders whose seats lost their money", () => {
    const round = verifiedRound();
    round.plan!.actions.push(
      { type: "stage_transport", community_id: "steinhatchee", seats: 30 },
      { type: "stage_transport", community_id: "steinhatchee", seats: 10 },
    );
    round.attack = { rationale: "", type: "budget_cut", percent: 10 };
    round.attacked = { ...round.result!, unfunded_actions: 1 };

    const attack = roundBeats(round, places)[2];

    expect(attack.shelters).toEqual({ "ruth-raines-ms": "open", "taylor-county-hs": "open" });
    expect(attack.unreached).toEqual({ steinhatchee: 10 });
  });
});

describe("people rerouting after the attack", () => {
  /** Taylor County High School offline: Cross City and Steinhatchee keep their shelter,
   * Perry's people have nowhere left to go. */
  function attackedRound(): Round {
    return {
      ...verifiedRound(),
      attacked_briefing: {
        conditions: [],
        limitations: [],
        neighborhoods: [
          neighborhood("perry", [], 299.56),
          neighborhood("cross-city", [["ruth-raines-ms", 204.52]]),
          neighborhood("steinhatchee", [["ruth-raines-ms", 63.84, 40]]),
          neighborhood(null, [["ruth-raines-ms", 168.2]], 201.3),
        ],
      },
    };
  }

  it("follows the attack and draws where people go under it", () => {
    const beats = roundBeats(attackedRound(), places);
    const [, , attack, reroute] = beats;

    expect(beats.map((b) => b.kind)).toEqual(["plan", "verdict", "attack", "reroute"]);
    expect(reroute.caption).toBe("Round 1 · People reroute: 453 of 960 still reach a shelter");
    expect(reroute.arcs).toEqual([
      { from: "cross-city", to: "ruth-raines-ms", people: 204.52, carried: 0, broken: false },
      { from: "steinhatchee", to: "ruth-raines-ms", people: 63.84, carried: 40, broken: false },
    ]);
    expect(reroute.unreached).toEqual({ perry: 299.56 });
    expect(reroute.shelters).toEqual(attack.shelters);
    expect(reroute.cutTowns).toEqual(attack.cutTowns);
    expect(reroute.figures).toEqual(attack.figures);
  });

  it("sends people to a shelter still open when theirs goes offline", () => {
    const round = attackedRound();
    round.attacked_briefing!.neighborhoods[0] = neighborhood("perry", [["ruth-raines-ms", 299.56]]);

    const reroute = roundBeats(round, places)[3];

    expect(reroute.arcs[0]).toEqual({
      from: "perry",
      to: "ruth-raines-ms",
      people: 299.56,
      carried: 0,
      broken: false,
    });
    expect(reroute.unreached).toEqual({});
  });

  it("is left out when the run did not record where people go under the attack", () => {
    expect(roundBeats(verifiedRound(), places).map((b) => b.kind)).toEqual([
      "plan",
      "verdict",
      "attack",
    ]);
  });
});
