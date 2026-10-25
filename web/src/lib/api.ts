// Types mirror the backend's Transcript and hazard layer responses.

export type Scenario = {
  budget: number;
  /** A community id for a single-town plan; null plans for the whole area. */
  scope: string | null;
  offline_shelters: string[];
  closed_communities: string[];
};

export type Action =
  | { type: "open_shelter"; shelter_id: string }
  | { type: "stage_transport"; community_id: string; seats: number }
  | { type: "allocate_budget"; category: "contingency_reserve"; amount: number };

export type Plan = {
  actions: Action[];
  claims: { cost: number; people_sheltered: number };
  rationale: string;
};

export type SimulationResult = {
  people_affected: number;
  people_sheltered: number;
  people_unreached: number;
  cost: number;
  robustness: number;
  unfunded_actions: number;
};

export type Check = {
  name: string;
  passed: boolean;
  claimed: number | null;
  actual: number | null;
  reason: string;
};

export type AgentCall = {
  model: string | null;
  provider: string | null;
  seconds: number;
  skipped: string[];
};

export type Round = {
  index: number;
  scenario: Scenario;
  plan: Plan | null;
  planner_error: string | null;
  planner_call: AgentCall | null;
  verdict: { passed: boolean; checks: Check[] } | null;
  result: SimulationResult | null;
  /** The Adversary's test of this plan: one failure; it never carries into later rounds. */
  attack: Attack | null;
  /** The plan's result with `attack` applied. */
  attacked: SimulationResult | null;
  adversary_error: string | null;
  adversary_call: AgentCall | null;
  /** Set when the Planner's output was invalid and this round re-tests an earlier plan. */
  plan_from_round: number | null;
  /** The plan written up under the conditions the user set. */
  report: PlanReport | null;
};

export type Assignment = {
  kind: "shelter" | "transport" | "reserve";
  title: string;
  resource: string;
  work: string;
  people: number | null;
  cost: number;
  funded: boolean;
};

export type ReportSection = { title: string; lines: string[] };

/** A plan written up as an operations plan, by the backend, under one set of conditions. */
export type PlanReport = {
  title: string;
  scenario: Scenario;
  result: SimulationResult;
  sections: ReportSection[];
  assignments: Assignment[];
  briefing: Briefing;
  evidence: EvidenceTrail;
  limitations: string[];
  references: SourceRef[];
};

/** A verified plan; the final plan shelters the most as planned, then the most on `typical`. */
export type Candidate = {
  /** Null for the plan code builds, which every run includes. */
  round_index: number | null;
  /** As planned. */
  result: SimulationResult;
  /** Average share sheltered over every single failure. */
  typical: number;
};

export type SourceRef = { id: string; title: string; origin: string };

/** Where one figure comes from; built by the backend from the same run that scored it. */
export type Evidence = {
  sources: SourceRef[];
  formula: string;
  inputs: string[];
  assumptions: string[];
  limitations: string[];
};

export type Figure = keyof SimulationResult | "budget";

export type EvidenceTrail = Partial<Record<Figure, Evidence>>;

export type ShelterAssignment = {
  shelter_id: string;
  name: string;
  people: number;
  carried: number;
};

export type NeighborhoodBriefing = {
  community_id: string | null; // null: people flooded outside every town
  name: string;
  people_affected: number;
  people_sheltered: number;
  people_unreached: number;
  shelters: ShelterAssignment[];
  transport_seats: number;
  road_closed: boolean;
  steps: string[];
};

export type Briefing = {
  conditions: string[];
  neighborhoods: NeighborhoodBriefing[];
  limitations: string[];
};

export type Recommendation = {
  /** Null when the plan code builds is final: it shelters more than every verified plan. */
  round_index: number | null;
  plan: Plan;
  /** As planned, under the base scenario. */
  result: SimulationResult;
  /** When the plan leaves people unsheltered: the cost of the cheapest set of shelters that
   * takes everyone, or null when no set can. */
  full_cover_cost: number | null;
  /** Written up under the base scenario: the conditions the plan is for. */
  report: PlanReport | null;
  stress: StressTest | null;
  /** Every failure the Adversary found, all at once. */
  combined: StressCase | null;
  candidates: Candidate[];
};

/** What to do instead when a failure hits: a plan built by code for those conditions. */
export type Backup = { actions: Action[]; result: SimulationResult };

export type StressCase = {
  attacks: Attack[];
  result: SimulationResult;
  /** Set when a backup plan shelters more people under these failures than the plan does. */
  backup: Backup | null;
};

/** The recommended plan under every single attack and every pair, worst first. */
export type StressTest = { cases: StressCase[] };

export type Attack = { rationale: string } & (
  | { type: "shelter_offline"; shelter_id: string }
  | { type: "road_closed"; community_id: string }
  | { type: "budget_cut"; percent: number }
);

export type Transcript = {
  base_scenario: Scenario;
  rounds: Round[];
  recommendation: Recommendation | null;
};

export type HazardLayerInfo = {
  method: string;
  bounds: { west: number; south: number; east: number; north: number };
  rows: number;
  cols: number;
  flagged_cells: number;
  // Null when the hazard method cannot tell open water from flooding under canopy.
  open_water_cells: number | null;
  under_canopy_cells: number | null;
  image_url: string;
};

export type ShelterInfo = {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  capacity: number;
  cost: number;
};

export type ExposureInfo = {
  total_population: number;
  people_in_flooded_cells: number;
  fema_zones_image_url: string;
  population_image_url: string;
  shelters: ShelterInfo[];
  communities: CommunityInfo[];
};

export type CommunityInfo = {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  radius_km: number;
  /** Shelters within its radius: a closed road does not cut the town off from these. */
  shelter_ids: string[];
};

export type FloodCells = {
  kinds: Record<string, string>; // FloodKind value -> name
  cells: [
    lon: number,
    lat: number,
    kind: number,
    confidence: number,
    people: number,
  ][];
};

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchHazard(): Promise<HazardLayerInfo> {
  return json(await fetch("/api/hazard"));
}

export async function fetchFloodCells(): Promise<FloodCells> {
  return json(await fetch("/api/flood-cells"));
}

export async function fetchExposure(): Promise<ExposureInfo> {
  return json(await fetch("/api/exposure"));
}

export type AgentKind = "gemma" | "rules";


export type LoopEvent =
  | { type: "started"; rounds: number }
  | { type: "round"; round: Round }
  | { type: "transcript"; transcript: Transcript }
  | { type: "error"; detail: string };

/** The base Scenario the user starts from. Keep in sync with BIG_BEND_SCENARIO in api/app.py. */
export const DEFAULT_SCENARIO: Scenario = {
  budget: 150_000,
  scope: null,
  offline_shelters: [],
  closed_communities: [],
};

export type RunOptions = {
  rounds: number;
  /** False for a quick re-plan: the Adversary skips the last round. */
  finalAttack: boolean;
  /** For a re-plan, the previous recommendation the Planner starts from. */
  previousPlan: Plan | null;
};

/** Runs the Loop on the server and calls `onEvent` for each event as it arrives. */
export async function streamLoop(
  agents: AgentKind,
  scenario: Scenario,
  options: RunOptions,
  onEvent: (event: LoopEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const query = `agents=${agents}&rounds=${options.rounds}&final_attack=${options.finalAttack}`;
  const response = await fetch(`/api/loop/stream?${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario, previous_plan: options.previousPlan }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as LoopEvent);
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as LoopEvent);
}

