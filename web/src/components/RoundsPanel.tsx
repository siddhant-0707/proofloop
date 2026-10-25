"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import {
  fetchExposure,
  streamLoop,
  type AgentCall,
  type AgentKind,
  type Attack,
  type Round,
  type Scenario,
  type SimulationResult,
  type Transcript,
} from "@/lib/api";
import { describeAttack, describeDamage, describePlan, type PlaceName } from "@/lib/describe";

// Rounds in a full stress test; a re-plan is one round.
const STRESS_TEST_ROUNDS = 3;
const people = (n: number) => Math.round(n).toLocaleString();
const dollars = (n: number) => `$${Math.round(n).toLocaleString()}`;

// Shelter or community id -> display name; falls back to the id until places load.
const PlaceNames = createContext<Record<string, string>>({});

function usePlaceName(): PlaceName {
  const names = useContext(PlaceNames);
  return (id: string) => names[id] ?? id;
}

const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

// Affected people outside FEMA flood zones, the people the unwarned attack keeps home.
const OutsideZones = createContext<number | null>(null);

function useAttackText() {
  const name = usePlaceName();
  const outside = useContext(OutsideZones);
  return (attack: Attack) => {
    const text = sentence(describeAttack(attack, name));
    return attack.type === "unwarned_outside_zone" && outside != null
      ? `${text} (${people(outside)} people)`
      : text;
  };
}

type Place = { id: string; name: string };

// Wait this long after the last control change before re-planning, so dragging the
// budget slider starts one run, not dozens.
const REPLAN_DELAY_MS = 700;

type RunKind = "stress test" | "re-plan";

export default function RoundsPanel({
  scenario,
  onScenarioChange,
}: {
  scenario: Scenario;
  onScenarioChange: (scenario: Scenario) => void;
}) {
  const [agents, setAgents] = useState<AgentKind>("gemma");
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [previous, setPrevious] = useState<Transcript | null>(null);
  const [kind, setKind] = useState<RunKind>("stress test");
  // Re-planning on every change starts once a full stress test has finished.
  const [canReplan, setCanReplan] = useState(false);
  const [liveRounds, setLiveRounds] = useState<Round[]>([]);
  const [totalRounds, setTotalRounds] = useState(STRESS_TEST_ROUNDS);
  const [shelters, setShelters] = useState<Place[]>([]);
  const [communities, setCommunities] = useState<Place[]>([]);
  const [outsideZones, setOutsideZones] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchExposure()
      .then((e) => {
        setShelters(e.shelters);
        setCommunities(e.communities);
        setOutsideZones(e.people_outside_fema_zones);
      })
      .catch(() => {});
    return () => abort.current?.abort();
  }, []);

  async function run(next: RunKind) {
    // A new run replaces any run still streaming, so stale rounds never show.
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setKind(next);
    setRunning(true);
    setStartedAt(Date.now());
    setError(null);
    if (transcript) setPrevious(transcript);
    setTranscript(null);
    setLiveRounds([]);
    try {
      await streamLoop(
        agents,
        scenario,
        next === "re-plan" ? 1 : STRESS_TEST_ROUNDS,
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === "started") setTotalRounds(event.rounds);
          else if (event.type === "round") setLiveRounds((done) => [...done, event.round]);
          else if (event.type === "transcript") {
            setTranscript(event.transcript);
            setCanReplan(true);
          } else setError(event.detail);
        },
        controller.signal,
      );
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (abort.current === controller) setRunning(false);
    }
  }

  // Every change to the base Scenario re-plans one round, once the debounce settles.
  const runRef = useRef(run);
  runRef.current = run;
  useEffect(() => {
    if (!canReplan) return;
    const timer = setTimeout(() => runRef.current("re-plan"), REPLAN_DELAY_MS);
    return () => clearTimeout(timer);
  }, [scenario, canReplan]);

  const names = useMemo(
    () => Object.fromEntries([...shelters, ...communities].map((p) => [p.id, p.name])),
    [shelters, communities],
  );
  const replan = kind === "re-plan";
  const rounds = transcript?.rounds ?? liveRounds;
  const idle = !running && !transcript && !error;

  return (
    <PlaceNames.Provider value={names}>
      <OutsideZones.Provider value={outsideZones}>
        <section className="flex h-full min-h-0 flex-col gap-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Stress test</h2>
              <p className="text-xs text-slate-500">
                Dixie and Taylor counties
                {shelters.length > 0 && `, ${shelters.length} public shelters`}
              </p>
              <AgentPicker value={agents} onChange={setAgents} disabled={running} />
            </div>
            <button
              type="button"
              onClick={() => run("stress test")}
              disabled={running && !replan}
              className="shrink-0 rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-wait disabled:opacity-60"
            >
              {running && !replan ? "Running…" : transcript ? "Run again" : "Run stress test"}
            </button>
          </div>

          <ScenarioControls
            scenario={scenario}
            onChange={onScenarioChange}
            shelters={shelters}
            communities={communities}
            canUnwarn={outsideZones != null}
            replans={canReplan}
          />

          {error && (
            <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-red-200">
              {error}
            </p>
          )}

          {idle && (
            <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
              The Planner proposes a plan, the Verifier recomputes its claims, and the Adversary
              attacks it before the next round. After the last round, one final attack decides
              which plan to recommend. After the first run, changing the conditions re-plans.
            </p>
          )}

          {(rounds.length > 0 || running) && (
            <ol className="flex min-h-0 flex-col gap-3 overflow-y-auto pb-1">
              {replan && previous?.recommendation && <Before transcript={previous} />}
              {rounds.map((round) => (
                <RoundCard
                  key={round.index}
                  round={round}
                  title={replan ? "Re-plan" : undefined}
                  recommended={transcript?.recommendation?.round_index === round.index}
                />
              ))}
              {running && !transcript && startedAt !== null && (
                <Progress
                  agents={agents}
                  done={rounds.length}
                  total={totalRounds}
                  replan={replan}
                  startedAt={startedAt}
                />
              )}
              {transcript && (
                <>
                  <FinalAttack transcript={transcript} />
                  <Recommendation transcript={transcript} replan={replan} />
                </>
              )}
            </ol>
          )}
        </section>
      </OutsideZones.Provider>
    </PlaceNames.Provider>
  );
}

const BUDGET = { min: 25_000, max: 250_000, step: 5_000 };

function ScenarioControls({
  scenario,
  onChange,
  shelters,
  communities,
  canUnwarn,
  replans,
}: {
  scenario: Scenario;
  onChange: (scenario: Scenario) => void;
  shelters: Place[];
  communities: Place[];
  canUnwarn: boolean;
  replans: boolean;
}) {
  const toggle = (list: string[], id: string) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
  return (
    <fieldset className="space-y-2.5 rounded-xl border border-slate-200 bg-white p-3.5 text-xs text-slate-700">
      <legend className="px-1 text-xs font-semibold text-slate-900">
        Conditions
        {replans && <span className="font-normal text-slate-500"> · changes re-plan</span>}
      </legend>
      <label className="block">
        <span className="flex justify-between">
          <span>Budget</span>
          <span className="tabular-nums font-medium text-slate-900">{dollars(scenario.budget)}</span>
        </span>
        <input
          type="range"
          min={BUDGET.min}
          max={BUDGET.max}
          step={BUDGET.step}
          value={scenario.budget}
          onChange={(e) => onChange({ ...scenario, budget: Number(e.target.value) })}
          className="mt-1 w-full accent-slate-900"
        />
      </label>
      {shelters.length > 0 && (
        <ChipGroup
          label="Shelter offline"
          options={shelters}
          selected={scenario.offline_shelters}
          onToggle={(id) =>
            onChange({ ...scenario, offline_shelters: toggle(scenario.offline_shelters, id) })
          }
        />
      )}
      {communities.length > 0 && (
        <ChipGroup
          label="Road closed"
          options={communities}
          selected={scenario.closed_communities}
          onToggle={(id) =>
            onChange({ ...scenario, closed_communities: toggle(scenario.closed_communities, id) })
          }
        />
      )}
      {canUnwarn && (
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={scenario.unwarned_outside_zones}
            onChange={(e) => onChange({ ...scenario, unwarned_outside_zones: e.target.checked })}
            className="accent-slate-900"
          />
          People outside FEMA flood zones are unwarned
        </label>
      )}
    </fieldset>
  );
}

function ChipGroup({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: Place[];
  selected: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <div>
      <p className="mb-1 text-slate-500">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const on = selected.includes(option.id);
          return (
            <button
              key={option.id}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(option.id)}
              className={`rounded-full px-2.5 py-1 font-medium ring-1 transition ${
                on
                  ? "bg-amber-50 text-amber-800 ring-amber-300"
                  : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {option.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Before({ transcript }: { transcript: Transcript }) {
  const name = usePlaceName();
  const rec = transcript.recommendation;
  if (!rec) return null;
  return (
    <li className="rounded-xl border border-dashed border-slate-300 p-3 text-xs text-slate-500">
      <span className="font-medium text-slate-700">Before the change:</span>{" "}
      {describePlan(rec.plan.actions, name)} · {people(rec.result.people_sheltered)} of{" "}
      {people(rec.result.people_affected)} sheltered with every attack applied
    </li>
  );
}

function Progress({
  agents,
  done,
  total,
  replan,
  startedAt,
}: {
  agents: AgentKind;
  done: number;
  total: number;
  replan: boolean;
  startedAt: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const who = agents === "gemma" ? "Gemma 4" : "The rule-based agents";
  const verb = agents === "gemma" ? "is" : "are";
  const step =
    done < total
      ? replan
        ? `${who} ${verb} re-planning for the new conditions`
        : `${who} ${verb} planning round ${done + 1} of ${total}`
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

function RoundCard({
  round,
  recommended,
  title,
}: {
  round: Round;
  recommended: boolean;
  title?: string;
}) {
  const name = usePlaceName();
  const attackText = useAttackText();
  const failed = round.verdict?.checks.filter((c) => !c.passed) ?? [];
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">
          {title ?? `Round ${round.index + 1}`}
        </h3>
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
            {attackText(round.attack)}
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
      {result.people_unreached_outside_zones >= 0.5 && (
        <p className="mt-1 text-xs text-slate-500">
          {people(result.people_unreached_outside_zones)} unreached people live outside FEMA flood
          zones
        </p>
      )}
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
  const attackText = useAttackText();
  if (transcript.final_adversary_error) {
    return <ErrorLine label="Adversary" message={transcript.final_adversary_error} />;
  }
  if (!transcript.final_attack) return null;
  return (
    <li className="rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-sm text-amber-800">
      <span className="font-semibold">Final attack:</span>{" "}
      {attackText(transcript.final_attack)}. No plan gets to answer it.
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

function Recommendation({ transcript, replan }: { transcript: Transcript; replan: boolean }) {
  const name = usePlaceName();
  const rec = transcript.recommendation;
  return (
    <li className="rounded-xl bg-slate-900 p-3.5 text-white">
      <h3 className="text-sm font-semibold">Recommendation</h3>
      {rec ? (
        <p className="mt-1 text-sm text-slate-200">
          {replan ? "The re-plan" : `Round ${rec.round_index + 1}'s plan`} ({describePlan(rec.plan.actions, name)}) holds
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
