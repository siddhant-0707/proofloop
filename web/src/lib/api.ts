// Types mirror the backend's Transcript and hazard layer responses.

export type Scenario = {
  budget: number;
  offline_shelters: string[];
  closed_communities: string[];
  unwarned_outside_zones: boolean;
};

export type Action =
  | { type: "open_shelter"; shelter_id: string }
  | { type: "stage_transport"; community_id: string; seats: number }
  | { type: "allocate_budget"; category: "contingency_reserve"; amount: number }
  | { type: "target_outreach"; community_id: string };

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
  people_unreached_outside_zones: number;
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
  attack: Attack | null;
  adversary_error: string | null;
  adversary_call: AgentCall | null;
};

export type Attack = { rationale: string } & (
  | { type: "shelter_offline"; shelter_id: string }
  | { type: "road_closed"; community_id: string }
  | { type: "budget_cut"; percent: number }
  | { type: "unwarned_outside_zone" }
);

export type Transcript = {
  base_scenario: Scenario;
  rounds: Round[];
  final_attack: Attack | null;
  final_adversary_error: string | null;
  final_adversary_call: AgentCall | null;
  final_scenario: Scenario;
  recommendation: { round_index: number; plan: Plan; result: SimulationResult } | null;
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
  people_outside_fema_zones: number | null;
  fema_zones_image_url: string;
  population_image_url: string;
  shelters: ShelterInfo[];
  communities: CommunityInfo[];
};

export type CommunityInfo = { id: string; name: string; latitude: number; longitude: number };

export type FloodCells = {
  kinds: Record<string, string>; // FloodKind value -> name
  cells: [
    lon: number,
    lat: number,
    kind: number,
    confidence: number,
    people: number,
    outsideFemaZones: number,
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
  offline_shelters: [],
  closed_communities: [],
  unwarned_outside_zones: false,
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

