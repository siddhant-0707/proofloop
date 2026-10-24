// Types mirror the backend's Transcript and hazard layer responses.

export type Scenario = { budget: number; offline_shelters: string[] };

export type Plan = {
  actions: { type: "open_shelter"; shelter_id: string }[];
  claims: { cost: number; people_sheltered: number };
  rationale: string;
};

export type SimulationResult = {
  people_affected: number;
  people_sheltered: number;
  people_unreached: number;
  cost: number;
  robustness: number;
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

export type Attack = { type: "shelter_offline"; shelter_id: string; rationale: string };

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
  population_image_url: string;
  shelters: ShelterInfo[];
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

export async function fetchExposure(): Promise<ExposureInfo> {
  return json(await fetch("/api/exposure"));
}

export type AgentKind = "gemma" | "rules";

export async function runLoop(agents: AgentKind): Promise<Transcript> {
  const path = agents === "gemma" ? "/api/loop/gemma" : "/api/loop";
  return json(await fetch(path, { method: "POST" }));
}

export async function runDemoLoop(): Promise<Transcript> {
  return json(await fetch("/api/loop/demo", { method: "POST" }));
}
