"use client";

import { useState } from "react";

import Logo from "@/components/Logo";
import type { AgentKind, Scenario } from "@/lib/api";
import { usePlaces } from "@/lib/places";

const MIN_BUDGET = 1_000;
const PRESETS = [100_000, 150_000, 250_000];

const ENGINES: { value: AgentKind; label: string; detail: string }[] = [
  { value: "gemma", label: "AI planner", detail: "Gemma 4 · about a minute or two" },
  { value: "rules", label: "Instant", detail: "Rule-based · a few seconds" },
];

const digits = (text: string) => text.replace(/\D/g, "");
const grouped = (text: string) => (text ? Number(text).toLocaleString("en-US") : "");

/** The start screen's card: what to plan for and the budget, then build the plan. */
export default function PlanSetup({
  scenario,
  agents,
  onScenarioChange,
  onAgentsChange,
  onRun,
  onBackToReport,
}: {
  scenario: Scenario;
  agents: AgentKind;
  onScenarioChange: (scenario: Scenario) => void;
  onAgentsChange: (agents: AgentKind) => void;
  onRun: (scenario: Scenario) => void;
  /** Set when a finished report can be reopened. */
  onBackToReport: (() => void) | null;
}) {
  const { communities } = usePlaces();
  const [budget, setBudget] = useState(String(scenario.budget));
  const amount = Number(budget);
  const valid = budget !== "" && amount >= MIN_BUDGET;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid) return;
    const next = { ...scenario, budget: amount };
    onScenarioChange(next);
    onRun(next);
  }

  return (
    <form
      onSubmit={submit}
      className="w-full max-w-sm overflow-hidden rounded-3xl bg-white/90 shadow-2xl shadow-slate-900/25 ring-1 ring-white/60 backdrop-blur-xl"
    >
      <div className="flex items-center gap-3 px-6 pt-6">
        <Logo className="size-10 drop-shadow-sm" />
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">cascade.ai</h1>
          <p className="text-xs text-slate-500">Disaster plans that survive the cascade</p>
        </div>
      </div>

      <div className="space-y-4 px-6 pt-4 pb-6">
        <Field label="Area">
          <div className="relative">
            <select
              aria-label="Area"
              value={scenario.scope ?? ""}
              onChange={(e) => onScenarioChange({ ...scenario, scope: e.target.value || null })}
              className="block w-full appearance-none rounded-xl border-0 bg-slate-50 py-2.5 pr-9 pl-3.5 text-sm font-medium text-slate-900 ring-1 ring-slate-200 transition hover:ring-slate-300 focus:ring-2 focus:ring-sky-500 focus:outline-none"
            >
              <option value="">Whole area · all towns</option>
              {communities.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <svg
              viewBox="0 0 20 20"
              className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-slate-400"
              aria-hidden
            >
              <path d="M5 8l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.8" />
            </svg>
          </div>
        </Field>

        <Field label="Budget">
          <div className="flex items-center rounded-xl bg-slate-50 ring-1 ring-slate-200 transition focus-within:ring-2 focus-within:ring-sky-500 hover:ring-slate-300">
            <span className="pl-3.5 text-sm font-medium text-slate-400">$</span>
            <input
              type="text"
              inputMode="numeric"
              aria-label="Budget in dollars"
              value={grouped(budget)}
              onChange={(e) => setBudget(digits(e.target.value))}
              className="w-full bg-transparent px-1.5 py-2.5 text-sm font-medium tabular-nums text-slate-900 focus:outline-none"
            />
          </div>
          <div className="mt-2 flex gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setBudget(String(p))}
                className={`flex-1 rounded-lg py-1 text-xs font-medium tabular-nums transition ${
                  amount === p
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                ${p / 1_000}k
              </button>
            ))}
          </div>
          {!valid && (
            <p className="mt-1.5 text-xs text-red-600">
              Enter at least ${MIN_BUDGET.toLocaleString("en-US")}.
            </p>
          )}
        </Field>

        <details className="group rounded-xl ring-1 ring-slate-200">
          <summary className="flex cursor-pointer list-none items-center justify-between px-3.5 py-2.5 text-xs font-medium text-slate-600">
            <span>
              Planning engine
              <span className="ml-1.5 text-slate-400">
                {ENGINES.find((e) => e.value === agents)?.label}
              </span>
            </span>
            <span className="text-slate-400 transition group-open:rotate-90" aria-hidden>
              ›
            </span>
          </summary>
          <div role="radiogroup" aria-label="Planning engine" className="grid gap-1.5 px-2 pb-2">
            {ENGINES.map((e) => (
              <button
                key={e.value}
                type="button"
                role="radio"
                aria-checked={agents === e.value}
                onClick={() => onAgentsChange(e.value)}
                className={`rounded-lg px-3 py-2 text-left transition ${
                  agents === e.value
                    ? "bg-sky-50 ring-1 ring-sky-300"
                    : "hover:bg-slate-50"
                }`}
              >
                <span className="block text-sm font-medium text-slate-900">{e.label}</span>
                <span className="block text-xs text-slate-500">{e.detail}</span>
              </button>
            ))}
          </div>
        </details>

        <button
          type="submit"
          disabled={!valid}
          className="group flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-sky-600 to-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-sky-900/20 transition hover:from-sky-500 hover:to-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Build plan
          <span className="transition group-hover:translate-x-0.5" aria-hidden>
            →
          </span>
        </button>
        {onBackToReport && (
          <button
            type="button"
            onClick={onBackToReport}
            className="w-full text-xs font-medium text-slate-500 transition hover:text-slate-900"
          >
            Back to the last report
          </button>
        )}
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      {children}
    </div>
  );
}
