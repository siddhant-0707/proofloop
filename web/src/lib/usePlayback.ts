"use client";

import { useEffect, useRef, useState } from "react";

import type { Beat } from "@/lib/storyboard";

// How long each beat stays on screen: a round (plan, verdict, attack, reroute) takes about 17 s.
const SHOWN_MS: Record<Beat["kind"], number> = {
  plan: 5_000,
  verdict: 3_000,
  attack: 5_000,
  reroute: 4_000,
  note: 3_000,
};

export type Playback = {
  /** The beat on the map, or null before the first one arrives. */
  beat: Beat | null;
  /** The current beat has had its time and the next has not arrived yet. */
  waiting: boolean;
  /** Every beat has played (or was skipped) and no more are coming. */
  finished: boolean;
  skip: () => void;
};

/** Plays beats one at a time, each for at least its time on screen, as they arrive.
 * `live` is true while more beats may still arrive; a new `run` starts over. */
export function usePlayback(beats: Beat[], live: boolean, run: number): Playback {
  const [state, setState] = useState({ run, index: 0, held: false, skipped: false });
  const current = state.run === run ? state : { run, index: 0, held: false, skipped: false };
  if (current !== state) setState(current);

  const { index, held, skipped } = current;
  const last = beats.length - 1;
  const kind = beats[index]?.kind;
  // Read when a beat's time is up, so a beat arriving meanwhile does not restart the clock.
  const lastRef = useRef(last);
  lastRef.current = last;

  useEffect(() => {
    if (skipped || held || !kind) return;
    const timer = setTimeout(
      () =>
        setState((s) =>
          s.index < lastRef.current ? { ...s, index: s.index + 1 } : { ...s, held: true },
        ),
      SHOWN_MS[kind],
    );
    return () => clearTimeout(timer);
  }, [kind, index, held, skipped]);

  // The next beat arrived while the current one was held: show it now.
  useEffect(() => {
    if (held && index < last) setState((s) => ({ ...s, index: s.index + 1, held: false }));
  }, [held, index, last]);

  const shown = skipped ? last : Math.min(index, last);
  const done = skipped || (held && index >= last) || beats.length === 0;
  return {
    beat: shown >= 0 ? beats[shown] : null,
    waiting: live && (skipped || beats.length === 0 || (held && index >= last)),
    finished: !live && done,
    skip: () => setState((s) => ({ ...s, skipped: true })),
  };
}
