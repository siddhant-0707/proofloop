"use client";

import { useEffect, useRef, useState } from "react";

import type { Transcript } from "@/lib/api";
import { dollars, people } from "@/lib/format";
import type { Figures } from "@/lib/storyboard";
import { plannedRounds, type LoopRun } from "@/lib/useLoopRun";
import type { Playback } from "@/lib/usePlayback";

/** A full-screen veil over the map for a question or an error once a run ends. */
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

/** The run playing on the map: a counter along the top and a caption bar along the bottom. */
export function RunStage({
  run,
  playback,
  onCancel,
}: {
  run: LoopRun;
  playback: Playback;
  onCancel: () => void;
}) {
  const { beat, waiting } = playback;
  return (
    <>
      {/* Leaves the map's zoom buttons uncovered on a phone. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-start p-4 pr-14 sm:justify-center sm:p-5">
        <RunFigures figures={beat?.figures ?? null} />
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex justify-center p-4 sm:p-6">
        <div className="pointer-events-auto w-full max-w-2xl overflow-hidden rounded-2xl bg-slate-950/85 text-white shadow-2xl ring-1 ring-white/10 backdrop-blur-md">
          <Steps run={run} playback={playback} />
          <div className="px-4 pt-2.5 pb-3 sm:px-5">
            <div className="flex items-center gap-3">
              <p className="min-w-0 flex-1 truncate text-[11px] font-medium uppercase tracking-[0.18em] text-sky-300">
                {run.kind === "re-plan" ? "Updating your plan" : `Building your plan · ${plannedRounds(run)} rounds`}
              </p>
              {beat?.verdict && !waiting && (
                <span
                  key={`${beat.caption}-stamp`}
                  className={`shrink-0 animate-stamp rounded-md border-2 px-2 py-0.5 text-xs font-bold uppercase tracking-widest ${
                    beat.verdict.passed ? "border-emerald-400 text-emerald-300" : "border-red-400 text-red-300"
                  }`}
                >
                  {beat.verdict.passed ? "Verified" : "Rejected"}
                </span>
              )}
              <button
                type="button"
                onClick={playback.skip}
                className="shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium text-white ring-1 ring-white/20 transition hover:bg-white/10"
              >
                Skip
              </button>
              <button
                type="button"
                onClick={onCancel}
                className="shrink-0 text-xs text-slate-400 transition hover:text-white"
              >
                Cancel
              </button>
            </div>
            {waiting ? (
              <p key="waiting" className="mt-1.5 flex animate-rise items-center gap-2 text-sm text-slate-200">
                <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-sky-400" aria-hidden />
                {waitingCaption(run)}…
              </p>
            ) : (
              beat && (
                <p key={beat.caption} className="mt-1.5 animate-rise text-sm text-white sm:text-[15px]">
                  {beat.caption}
                </p>
              )
            )}
          </div>
        </div>
      </div>
    </>
  );
}

/** One segment per round, then one for the report: done, playing (pulsing) or to come. */
function Steps({ run, playback }: { run: LoopRun; playback: Playback }) {
  const rounds = plannedRounds(run);
  const { beat, waiting, finished } = playback;
  // The current round counts as told once its verdict is showing.
  const roundsTold = beat ? beat.round - (beat.kind === "plan" ? 1 : 0) : 0;
  const current = waiting ? run.rounds.length : beat ? beat.round - 1 : 0;
  return (
    <div className="flex gap-1 px-4 pt-3 sm:px-5" aria-hidden>
      {Array.from({ length: rounds + 1 }, (_, i) => {
        const done = finished || i < roundsTold;
        return (
          <span
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors duration-500 ${
              done
                ? "bg-gradient-to-r from-sky-400 to-emerald-400"
                : i === current
                  ? "animate-pulse bg-sky-400/60"
                  : "bg-white/10"
            }`}
          />
        );
      })}
    </div>
  );
}

/** What the run is doing while the next beat is on its way. */
function waitingCaption(run: LoopRun): string {
  if (run.rounds.length >= plannedRounds(run)) {
    return "Testing the plan against every failure and writing your report";
  }
  const who = run.agents === "gemma" ? "Gemma 4" : "The rule-based planner";
  const round = `Round ${run.rounds.length + 1}`;
  return run.rounds.length === 0
    ? `${round} · ${who} is drafting a plan`
    : `${round} · ${who} is attacking the last plan and drafting a stronger one`;
}

function RunFigures({ figures }: { figures: Figures | null }) {
  return (
    <dl className="pointer-events-auto grid grid-cols-3 divide-x divide-white/10 overflow-hidden rounded-2xl bg-slate-950/85 text-white shadow-2xl ring-1 ring-white/10 backdrop-blur-md">
      <Figure label="People at risk" value={figures?.atRisk} format={people} />
      <Figure label="Sheltered" value={figures?.sheltered} format={people} accent />
      <Figure
        label="Budget used"
        value={figures?.budgetUsed}
        format={dollars}
        note={
          figures
            ? `of ${dollars(figures.budget)}${figures.reserve ? ` · ${dollars(figures.reserve)} held back` : ""}`
            : undefined
        }
      />
    </dl>
  );
}

function Figure(props: {
  label: string;
  value: number | undefined;
  format: (n: number) => string;
  accent?: boolean;
  note?: string;
}) {
  const shown = useTween(props.value);
  return (
    <div className="px-3 py-2 sm:px-5 sm:py-2.5">
      <dt className="text-[10px] uppercase tracking-wide text-slate-400 sm:text-[11px]">{props.label}</dt>
      <dd
        className={`text-lg font-semibold tabular-nums sm:text-2xl ${props.accent ? "text-emerald-300" : ""}`}
      >
        {shown == null ? "–" : props.format(shown)}
      </dd>
      {props.note && <dd className="text-[10px] text-slate-400 sm:text-[11px]">{props.note}</dd>}
    </div>
  );
}

/** Eases a number to each new value, so the counter rolls rather than jumps. */
function useTween(target: number | undefined): number | undefined {
  const [shown, setShown] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (target == null) {
      // The next run's counter rolls up from zero.
      from.current = undefined;
      setShown(undefined);
      return;
    }
    const start = from.current ?? 0;
    const began = performance.now();
    let frame = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - began) / 700);
      const value = start + (target - start) * (1 - (1 - k) ** 3);
      from.current = value;
      setShown(value);
      if (k < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target]);
  return shown;
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
