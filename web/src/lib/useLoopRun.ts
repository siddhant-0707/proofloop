"use client";

import { useEffect, useRef, useState } from "react";

import { streamLoop, type AgentKind, type Scenario, type Transcript } from "@/lib/api";

// Rounds in a full stress test; a re-plan is one round.
const STRESS_TEST_ROUNDS = 3;

export type RunKind = "stress test" | "re-plan";

export type LoopRun = {
  kind: RunKind;
  agents: AgentKind;
  running: boolean;
  /** Steps finished: rounds so far, out of `steps` (the rounds plus writing the report). */
  done: number;
  steps: number;
  startedAt: number | null;
  /** When the last step finished, for estimating progress through the current one. */
  lastStepAt: number | null;
  transcript: Transcript | null;
  /** The transcript before this run, for a re-plan's "plan before the change". */
  previous: Transcript | null;
  error: string | null;
};

const IDLE: LoopRun = {
  kind: "stress test",
  agents: "gemma",
  running: false,
  done: 0,
  steps: STRESS_TEST_ROUNDS + 1,
  startedAt: null,
  lastStepAt: null,
  transcript: null,
  previous: null,
  error: null,
};

/** Streams Loop runs from the server; a new run replaces any run still streaming. */
export function useLoopRun() {
  const [state, setState] = useState<LoopRun>(IDLE);
  const abort = useRef<AbortController | null>(null);
  const latest = useRef(state);
  latest.current = state;

  useEffect(() => () => abort.current?.abort(), []);

  async function start(kind: RunKind, agents: AgentKind, scenario: Scenario) {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    const prior = latest.current.transcript;
    const rounds = kind === "re-plan" ? 1 : STRESS_TEST_ROUNDS;
    const now = Date.now();
    setState({
      ...IDLE,
      kind,
      agents,
      running: true,
      steps: rounds + 1,
      startedAt: now,
      lastStepAt: now,
      previous: prior,
    });
    const update = (change: Partial<LoopRun>) => {
      if (!controller.signal.aborted) setState((s) => ({ ...s, ...change }));
    };
    try {
      await streamLoop(
        agents,
        scenario,
        kind === "re-plan"
          ? { rounds, finalAttack: false, previousPlan: prior?.recommendation?.plan ?? null }
          : { rounds, finalAttack: true, previousPlan: null },
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === "started") update({ steps: event.rounds + 1 });
          else if (event.type === "round") {
            setState((s) => ({ ...s, done: s.done + 1, lastStepAt: Date.now() }));
          } else if (event.type === "transcript") {
            update({ transcript: event.transcript, done: latest.current.steps });
          } else update({ error: event.detail });
        },
        controller.signal,
      );
    } catch (e) {
      update({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      if (abort.current === controller) update({ running: false });
    }
  }

  function cancel() {
    abort.current?.abort();
    setState((s) => ({ ...s, running: false }));
  }

  function reset() {
    abort.current?.abort();
    setState(IDLE);
  }

  return { run: state, start, cancel, reset };
}
