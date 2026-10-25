"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";

import {
  fetchExposure,
  streamLoop,
  type AgentCall,
  type AgentKind,
  type Round,
  type SimulationResult,
  type Transcript,
} from "@/lib/api";
import { describeAttack, describeDamage, describePlan, type PlaceName } from "@/lib/describe";

const people = (n: number) => Math.round(n).toLocaleString();
const dollars = (n: number) => `$${Math.round(n).toLocaleString()}`;

// Shelter or community id -> display name; falls back to the id until places load.
const PlaceNames = createContext<Record<string, string>>({});

function usePlaceName(): PlaceName {
  const names = useContext(PlaceNames);
  return (id: string) => names[id] ?? id;
}

const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export default function RoundsPanel() {
  const [agents, setAgents] = useState<AgentKind>("gemma");
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [liveRounds, setLiveRounds] = useState<Round[]>([]);
  const [totalRounds, setTotalRounds] = useState(3);
  const [names, setNames] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchExposure()
      .then((e) =>
        setNames(Object.fromEntries([...e.shelters, ...e.communities].map((p) => [p.id, p.name]))),
      )
      .catch(() => {});
    return () => abort.current?.abort();
  }, []);

  async function run() {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setRunning(true);
    setStartedAt(Date.now());
    setError(null);
    setTranscript(null);
    setLiveRounds([]);
    try {
      await streamLoop(
        agents,
        (event) => {
          if (event.type === "started") setTotalRounds(event.rounds);
          else if (event.type === "round") setLiveRounds((rounds) => [...rounds, event.round]);
          else if (event.type === "transcript") setTranscript(event.transcript);
          else setError(event.detail);
        },
        controller.signal,
      );
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (abort.current === controller) setRunning(false);
    }
  }

  const rounds = transcript?.rounds ?? liveRounds;
  const idle = !running && !transcript && !error;

  return (
    <PlaceNames.Provider value={names}>
      <section className="flex h-full min-h-0 flex-col gap-3">
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

        {idle && (
          <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
            The Planner proposes a plan, the Verifier recomputes its claims, and the Adversary
            knocks out a shelter before the next round. After the last round, one final attack
            decides which plan to recommend.
          </p>
        )}

        {(rounds.length > 0 || running) && (
          <ol className="flex min-h-0 flex-col gap-3 overflow-y-auto pb-1">
            {rounds.map((round) => (
              <RoundCard
                key={round.index}
                round={round}
                recommended={transcript?.recommendation?.round_index === round.index}
              />
            ))}
            {running && !transcript && startedAt !== null && (
              <Progress
                agents={agents}
                done={rounds.length}
                total={totalRounds}
                startedAt={startedAt}
              />
            )}
            {transcript && (
              <>
                <FinalAttack transcript={transcript} />
                <Recommendation transcript={transcript} />
              </>
            )}
          </ol>
        )}
      </section>
    </PlaceNames.Provider>
  );
}

function Progress({
  agents,
  done,
  total,
  startedAt,
}: {
  agents: AgentKind;
  done: number;
  total: number;
  startedAt: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const who = agents === "gemma" ? "Gemma 4" : "The rule-based agents";
  const step =
    done < total
      ? `${who} ${agents === "gemma" ? "is" : "are"} planning round ${done + 1} of ${total}`
      : "Choosing the final attack and the recommendation";
  return (
    <li
      aria-live="polite"
      className="flex items-center gap-3 rounded-xl border border-dashed border-slate-300 p-3.5 text-sm text-slate-600"
    >
      <span className="size-2 shrink-0 animate-pulse rounded-full bg-slate-900" aria-hidden />
      <span className="flex-1">{step}…</span>
      <span className="tabular-nums text-xs text-slate-400">
        {Math.floor((now - startedAt) / 1000)} s
      </span>
    </li>
  );
}

function RoundCard({ round, recommended }: { round: Round; recommended: boolean }) {
  const name = usePlaceName();
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
        Going in: {describeDamage(round.scenario, name)} · budget {dollars(round.scenario.budget)}
      </p>

      {round.planner_error && <ErrorLine label="Planner" message={round.planner_error} />}
      {round.plan && (
        <p className="mt-2 text-sm text-slate-700">
          <span className="font-medium text-slate-900">Plan:</span>{" "}
          {describePlan(round.plan.actions, name)}
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
            <span className="font-medium">Attack:</span>{" "}
            {sentence(describeAttack(round.attack, name))}
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
      {result.unfunded_actions > 0 && (
        <p className="mt-1 text-xs text-amber-700">
          {result.unfunded_actions} action{result.unfunded_actions === 1 ? "" : "s"} left without
          money by the budget
        </p>
      )}
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-slate-900" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function FinalAttack({ transcript }: { transcript: Transcript }) {
  const name = usePlaceName();
  if (transcript.final_adversary_error) {
    return <ErrorLine label="Adversary" message={transcript.final_adversary_error} />;
  }
  if (!transcript.final_attack) return null;
  return (
    <li className="rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-sm text-amber-800">
      <span className="font-semibold">Final attack:</span>{" "}
      {sentence(describeAttack(transcript.final_attack, name))}. No plan gets to answer it.
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
  const name = usePlaceName();
  const rec = transcript.recommendation;
  return (
    <li className="rounded-xl bg-slate-900 p-3.5 text-white">
      <h3 className="text-sm font-semibold">Recommendation</h3>
      {rec ? (
        <p className="mt-1 text-sm text-slate-200">
          Round {rec.round_index + 1}&apos;s plan ({describePlan(rec.plan.actions, name)}) holds
          up best with every attack applied ({describeDamage(transcript.final_scenario, name)};
          budget {dollars(transcript.final_scenario.budget)}):{" "}
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
