"use client";

import { createContext, useContext, useEffect, useState } from "react";

import {
  fetchExposure,
  runLoop,
  type AgentCall,
  type AgentKind,
  type Plan,
  type Round,
  type SimulationResult,
  type Transcript,
} from "@/lib/api";

const people = (n: number) => Math.round(n).toLocaleString();
const dollars = (n: number) => `$${Math.round(n).toLocaleString()}`;
const shelterIds = (plan: Plan) => [...new Set(plan.actions.map((a) => a.shelter_id))];

// Shelter id -> display name; falls back to the id until shelters load.
const ShelterNames = createContext<Record<string, string>>({});

function useShelterName() {
  const names = useContext(ShelterNames);
  return (id: string) => names[id] ?? id;
}

function useShelterList() {
  const name = useShelterName();
  return (ids: string[]) => (ids.length ? ids.map(name).join(", ") : "none");
}

export default function RoundsPanel() {
  const [agents, setAgents] = useState<AgentKind>("gemma");
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchExposure()
      .then((e) => setNames(Object.fromEntries(e.shelters.map((s) => [s.id, s.name]))))
      .catch(() => {});
  }, []);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      setTranscript(await runLoop(agents));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <ShelterNames.Provider value={names}>
      <section className="flex h-full flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Stress test</h2>
            <p className="text-xs text-slate-500">
              Dixie and Taylor counties, 4 public shelters
              {transcript && `. Budget ${dollars(transcript.base_scenario.budget)}`}.
            </p>
            <AgentPicker value={agents} onChange={setAgents} disabled={running} />
          </div>
          <button
            type="button"
            onClick={run}
            disabled={running}
            className="shrink-0 rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-wait disabled:opacity-60"
          >
            {running ? "Running…" : transcript ? "Run again" : "Run stress test"}
          </button>
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-red-200">
            {error}
          </p>
        )}

        {!transcript && !error && (
          <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
            The Planner proposes a plan, the Verifier recomputes its claims, and the Adversary
            knocks out a shelter before the next round. After the last round, one final attack
            decides which plan to recommend.
          </p>
        )}

        {transcript && (
          <ol className="flex flex-col gap-3 overflow-y-auto pb-1">
            {transcript.rounds.map((round) => (
              <RoundCard
                key={round.index}
                round={round}
                recommended={transcript.recommendation?.round_index === round.index}
              />
            ))}
            <FinalAttack transcript={transcript} />
            <Recommendation transcript={transcript} />
          </ol>
        )}
      </section>
    </ShelterNames.Provider>
  );
}

function RoundCard({ round, recommended }: { round: Round; recommended: boolean }) {
  const shelterList = useShelterList();
  const shelterName = useShelterName();
  const failed = round.verdict?.checks.filter((c) => !c.passed) ?? [];
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Round {round.index + 1}</h3>
        <div className="flex gap-1.5">
          {recommended && <Badge tone="blue">Recommended</Badge>}
          {round.verdict &&
            (round.verdict.passed ? (
              <Badge tone="green">Verified</Badge>
            ) : (
              <Badge tone="red">Rejected</Badge>
            ))}
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Offline going in: {shelterList(round.scenario.offline_shelters)}
      </p>

      {round.planner_error && <ErrorLine label="Planner" message={round.planner_error} />}
      {round.plan && (
        <p className="mt-2 text-sm text-slate-700">
          <span className="font-medium text-slate-900">Plan:</span> open shelters{" "}
          {shelterList(shelterIds(round.plan))}
        </p>
      )}
      {round.result && <Score result={round.result} />}
      {round.plan?.rationale && (
        <p className="mt-2 text-xs leading-relaxed text-slate-600">{round.plan.rationale}</p>
      )}
      {round.planner_call && <CallLine label="Planner" call={round.planner_call} />}

      {failed.length > 0 && (
        <ul className="mt-2 space-y-1 rounded-lg bg-red-50 p-2 text-xs text-red-700">
          {failed.map((c) => (
            <li key={c.name}>
              <span className="font-medium">{c.name.replaceAll("_", " ")}:</span> {c.reason}
            </li>
          ))}
        </ul>
      )}

      {round.adversary_error && <ErrorLine label="Adversary" message={round.adversary_error} />}
      {round.attack && (
        <div className="mt-2 border-t border-slate-100 pt-2">
          <p className="text-xs text-amber-700">
            <span className="font-medium">Attack:</span> {shelterName(round.attack.shelter_id)}{" "}
            goes offline
          </p>
          {round.attack.rationale && (
            <p className="mt-1 text-xs leading-relaxed text-slate-600">{round.attack.rationale}</p>
          )}
          {round.adversary_call && <CallLine label="Adversary" call={round.adversary_call} />}
        </div>
      )}
    </li>
  );
}

const AGENTS: { value: AgentKind; label: string }[] = [
  { value: "gemma", label: "Gemma 4" },
  { value: "rules", label: "Rule-based" },
];

function AgentPicker({
  value,
  onChange,
  disabled,
}: {
  value: AgentKind;
  onChange: (agents: AgentKind) => void;
  disabled: boolean;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Agents"
      className="mt-2 inline-flex rounded-lg bg-slate-100 p-0.5 text-xs"
    >
      {AGENTS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          disabled={disabled}
          onClick={() => onChange(option.value)}
          className={`rounded-md px-2.5 py-1 font-medium transition disabled:cursor-not-allowed ${
            value === option.value
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function CallLine({ label, call }: { label: string; call: AgentCall }) {
  if (!call.model) return null; // rule-based agents
  const n = call.skipped.length;
  const fallback = n ? ` after ${n} fallback${n === 1 ? "" : "s"}` : "";
  return (
    <p
      className="mt-1.5 text-[11px] text-slate-400"
      title={call.skipped.length ? call.skipped.join("\n") : undefined}
    >
      {label}: {call.model} via {call.provider} · {call.seconds.toFixed(1)} s{fallback}
    </p>
  );
}

function Score({ result }: { result: SimulationResult }) {
  const pct = Math.round(result.robustness * 100);
  return (
    <div className="mt-2">
      <div className="flex justify-between text-xs text-slate-600">
        <span>
          {people(result.people_sheltered)} of {people(result.people_affected)} people sheltered
        </span>
        <span className="tabular-nums">
          {pct}% · {dollars(result.cost)}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-slate-900" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function FinalAttack({ transcript }: { transcript: Transcript }) {
  const shelterName = useShelterName();
  if (transcript.final_adversary_error) {
    return <ErrorLine label="Adversary" message={transcript.final_adversary_error} />;
  }
  if (!transcript.final_attack) return null;
  return (
    <li className="rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-sm text-amber-800">
      <span className="font-semibold">Final attack:</span>{" "}
      {shelterName(transcript.final_attack.shelter_id)} goes offline. No plan gets to answer it.
      {transcript.final_attack.rationale && (
        <p className="mt-1 text-xs leading-relaxed text-amber-900/80">
          {transcript.final_attack.rationale}
        </p>
      )}
      {transcript.final_adversary_call && (
        <CallLine label="Adversary" call={transcript.final_adversary_call} />
      )}
    </li>
  );
}

function Recommendation({ transcript }: { transcript: Transcript }) {
  const shelterList = useShelterList();
  const rec = transcript.recommendation;
  return (
    <li className="rounded-xl bg-slate-900 p-3.5 text-white">
      <h3 className="text-sm font-semibold">Recommendation</h3>
      {rec ? (
        <p className="mt-1 text-sm text-slate-200">
          Round {rec.round_index + 1}&apos;s plan (open {shelterList(shelterIds(rec.plan))}) holds
          up best with every attack applied (offline:{" "}
          {shelterList(transcript.final_scenario.offline_shelters)}):{" "}
          {people(rec.result.people_sheltered)} of {people(rec.result.people_affected)} people
          sheltered.
        </p>
      ) : (
        <p className="mt-1 text-sm text-slate-300">No plan passed verification.</p>
      )}
    </li>
  );
}

function ErrorLine({ label, message }: { label: string; message: string }) {
  return (
    <p className="mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
      <span className="font-medium">{label} output rejected:</span> {message}
    </p>
  );
}

function Badge({ tone, children }: { tone: "green" | "red" | "blue"; children: React.ReactNode }) {
  const tones = {
    green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    red: "bg-red-50 text-red-700 ring-red-200",
    blue: "bg-blue-50 text-blue-700 ring-blue-200",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${tones[tone]}`}>
      {children}
    </span>
  );
}
