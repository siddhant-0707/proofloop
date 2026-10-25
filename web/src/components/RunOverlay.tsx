"use client";

import { useEffect, useState } from "react";

import type { Transcript } from "@/lib/api";
import { dollars, people } from "@/lib/format";
import type { LoopRun } from "@/lib/useLoopRun";

const STAGES = [
  { title: "Draft", detail: "Drafting a shelter plan for the flooded area" },
  { title: "Strengthen", detail: "Checking it against closed shelters, roads and budget cuts" },
  { title: "Finish", detail: "Preparing backup plans and your report" },
];

/** A full-screen veil over the map while a run plays: progress, then any question. */
export function RunVeil({ children }: { children: React.ReactNode }) {
  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center bg-gradient-to-b from-slate-950/70 via-slate-950/55 to-slate-950/75 p-4 backdrop-blur-[2px]">
      {children}
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full max-w-md rounded-3xl bg-slate-900/80 p-7 text-white shadow-2xl ring-1 ring-white/10 backdrop-blur-md">
      {children}
    </div>
  );
}

export function RunProgress({ run, onCancel }: { run: LoopRun; onCancel: () => void }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(timer);
  }, []);
  const fraction = progress(run, now);
  const stage = run.done === 0 ? 0 : run.done < run.steps - 1 ? 1 : 2;
  const elapsed = run.startedAt ? Math.max(0, Math.floor((now - run.startedAt) / 1000)) : 0;
  return (
    <Card>
      <p className="text-center text-xs font-medium uppercase tracking-[0.2em] text-sky-300">
        {run.kind === "re-plan" ? "Updating your plan" : "Building your plan"}
      </p>
      <div className="mt-5 flex justify-center">
        <Ring fraction={fraction}>
          <span className="text-4xl font-semibold tabular-nums">{Math.floor(fraction * 100)}%</span>
          <span className="mt-1 text-xs tabular-nums text-slate-400">{clock(elapsed)} elapsed</span>
        </Ring>
      </div>
      <ol className="mt-6 grid grid-cols-3 gap-2">
        {STAGES.map((s, i) => (
          <li key={s.title} className="flex flex-col items-center gap-1.5 text-xs">
            <span
              className={`flex size-6 items-center justify-center rounded-full text-[11px] font-semibold transition ${
                i < stage
                  ? "bg-emerald-400 text-slate-900"
                  : i === stage
                    ? "bg-sky-400 text-slate-900 ring-4 ring-sky-400/25"
                    : "bg-white/10 text-slate-400"
              }`}
            >
              {i < stage ? "✓" : i + 1}
            </span>
            <span className={i === stage ? "font-medium text-white" : "text-slate-400"}>{s.title}</span>
          </li>
        ))}
      </ol>
      <p className="mt-4 flex items-center justify-center gap-2 text-center text-sm text-slate-300">
        <span className="size-1.5 animate-pulse rounded-full bg-sky-400" aria-hidden />
        {STAGES[stage].detail}…
      </p>
      <button
        type="button"
        onClick={onCancel}
        className="mx-auto mt-5 block text-xs text-slate-400 transition hover:text-white"
      >
        Cancel
      </button>
    </Card>
  );
}

/** Share of the run done: finished steps, plus an estimate of the current one that slows as it
 * goes, so the number keeps moving but never reaches 100% before the run does. */
function progress(run: LoopRun, now: number): number {
  if (!run.running) return 1;
  const final = run.done >= run.steps - 1;
  const typical = final ? 4_000 : run.agents === "gemma" ? 40_000 : 600;
  const since = run.lastStepAt ? now - run.lastStepAt : 0;
  const current = 1 - Math.exp(-since / typical);
  return Math.min(0.99, (run.done + 0.95 * current) / run.steps);
}

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function Ring({ fraction, children }: { fraction: number; children: React.ReactNode }) {
  const r = 70;
  const around = 2 * Math.PI * r;
  return (
    <div className="relative size-44">
      <svg viewBox="0 0 160 160" className="size-full -rotate-90">
        <defs>
          <linearGradient id="run-ring" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="100%" stopColor="#34d399" />
          </linearGradient>
        </defs>
        <circle cx="80" cy="80" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />
        <circle
          cx="80"
          cy="80"
          r={r}
          fill="none"
          stroke="url(#run-ring)"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={around}
          strokeDashoffset={around * (1 - fraction)}
          className="transition-[stroke-dashoffset] duration-300 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">{children}</div>
    </div>
  );
}

/** The cheapest budget that would shelter everyone, when money alone keeps the plan short. */
export function budgetShortfall(transcript: Transcript | null): number | null {
  const rec = transcript?.recommendation;
  if (!rec?.report || rec.result.people_unreached < 0.5 || rec.full_cover_cost == null) return null;
  return rec.full_cover_cost > rec.report.scenario.budget ? rec.full_cover_cost : null;
}

export function BudgetQuestion({
  transcript,
  needed,
  onRaise,
  onKeep,
}: {
  transcript: Transcript;
  needed: number;
  onRaise: () => void;
  onKeep: () => void;
}) {
  const rec = transcript.recommendation!;
  const budget = rec.report!.scenario.budget;
  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-[0.2em] text-amber-300">Budget check</p>
      <h2 className="mt-2 text-xl font-semibold">No plan within {dollars(budget)} shelters everyone.</h2>
      <dl className="mt-5 grid grid-cols-2 gap-3">
        <div className="rounded-2xl bg-white/5 p-3 ring-1 ring-white/10">
          <dt className="text-[11px] uppercase tracking-wide text-slate-400">Now · {dollars(budget)}</dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums">
            {people(rec.result.people_sheltered)}
            <span className="text-sm font-normal text-slate-400">
              {" "}
              of {people(rec.result.people_affected)}
            </span>
          </dd>
          <dd className="text-xs text-slate-400">people sheltered</dd>
        </div>
        <div className="rounded-2xl bg-emerald-400/10 p-3 ring-1 ring-emerald-400/30">
          <dt className="text-[11px] uppercase tracking-wide text-emerald-300">
            Needed · {dollars(needed)}
          </dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums">
            {people(rec.result.people_affected)}
            <span className="text-sm font-normal text-slate-400">
              {" "}
              of {people(rec.result.people_affected)}
            </span>
          </dd>
          <dd className="text-xs text-slate-400">everyone sheltered</dd>
        </div>
      </dl>
      <p className="mt-4 text-sm text-slate-300">
        {dollars(needed)} is the lowest budget that opens shelters for everyone affected. Raise
        the budget and update the plan?
      </p>
      <div className="mt-5 flex gap-2">
        <button
          type="button"
          onClick={onRaise}
          className="flex-1 rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-slate-900 transition hover:bg-slate-200"
        >
          Yes, use {dollars(needed)}
        </button>
        <button
          type="button"
          onClick={onKeep}
          className="flex-1 rounded-xl px-4 py-2.5 text-sm font-medium text-white ring-1 ring-white/20 transition hover:bg-white/10"
        >
          No, keep {dollars(budget)}
        </button>
      </div>
    </Card>
  );
}

export function RunError({ error, onBack }: { error: string; onBack: () => void }) {
  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-[0.2em] text-red-300">Run failed</p>
      <p className="mt-2 text-sm text-slate-200">{error}</p>
      <button
        type="button"
        onClick={onBack}
        className="mt-5 w-full rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-slate-900 transition hover:bg-slate-200"
      >
        Back
      </button>
    </Card>
  );
}
