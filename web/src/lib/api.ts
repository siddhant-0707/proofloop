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

export type Round = {
  index: number;
  scenario: Scenario;
  plan: Plan | null;
  planner_error: string | null;
  verdict: { passed: boolean; checks: Check[] } | null;
  result: SimulationResult | null;
  attack: Attack | null;
  adversary_error: string | null;
};

export type Attack = { type: "shelter_offline"; shelter_id: string };

export type Transcript = {
  base_scenario: Scenario;
  rounds: Round[];
  final_attack: Attack | null;
  final_adversary_error: string | null;
  final_scenario: Scenario;
  recommendation: { round_index: number; plan: Plan; result: SimulationResult } | null;
};

export type HazardLayerInfo = {
  method: string;
  bounds: { west: number; south: number; east: number; north: number };
  rows: number;
  cols: number;
  flagged_cells: number;
  image_url: string;
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

export async function runDemoLoop(): Promise<Transcript> {
  return json(await fetch("/api/loop/demo", { method: "POST" }));
}
