"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { EvidenceProvider } from "@/components/EvidenceDrawer";
import HazardMap from "@/components/HazardMap";
import Logo from "@/components/Logo";
import PlanReport, {
  PRINT_PARTS,
  PrintableReport,
  alternatives,
  type Alternative,
  type PrintPart,
} from "@/components/PlanReport";
import PlanSetup from "@/components/PlanSetup";
import {
  BudgetQuestion,
  RunError,
  RunStage,
  RunVeil,
  budgetShortfall,
} from "@/components/RunOverlay";
import { DEFAULT_SCENARIO, type AgentKind, type Scenario, type Transcript } from "@/lib/api";
import { dollars } from "@/lib/format";
import { PlacesProvider, usePlaceName, usePlaces } from "@/lib/places";
import { roundBeats } from "@/lib/storyboard";
import { useLoopRun } from "@/lib/useLoopRun";
import { usePlayback } from "@/lib/usePlayback";

/** Three screens over one map: choose what to plan, watch the run, read the plan report. */
export default function Dashboard() {
  return (
    <PlacesProvider>
      <EvidenceProvider>
        <Screens />
      </EvidenceProvider>
    </PlacesProvider>
  );
}

function Screens() {
  const name = usePlaceName();
  const [scenario, setScenario] = useState<Scenario>(DEFAULT_SCENARIO);
  const [agents, setAgents] = useState<AgentKind>("gemma");
  const [showReport, setShowReport] = useState(false);
  // The run whose budget question was answered "keep the budget".
  const [kept, setKept] = useState<Transcript | null>(null);
  const { run, start, reset } = useLoopRun();
  const { names, sheltersIn } = usePlaces();
  const beats = useMemo(() => {
    const places = { name: (id: string) => names[id] ?? id, sheltersIn };
    return run.rounds.flatMap((r) => roundBeats(r, places));
  }, [run.rounds, names, sheltersIn]);
  const playback = usePlayback(beats, run.running, run.startedAt ?? 0);
  const [printing, setPrinting] = useState<{
    part: PrintPart;
    plan?: string;
    map: string | null;
    file: string;
  } | null>(null);

  const transcript = run.transcript;
  const needed = budgetShortfall(transcript);
  const asking = !run.running && transcript && needed != null && kept !== transcript;

  useEffect(() => {
    if (transcript) setShowReport(true);
  }, [transcript]);

  useEffect(() => {
    if (!printing) return;
    const title = document.title;
    document.title = printing.file;
    const done = () => setPrinting(null);
    window.addEventListener("afterprint", done);
    // Leaves time for the print view and its map image to render.
    const timer = setTimeout(() => window.print(), 400);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("afterprint", done);
      document.title = title;
    };
  }, [printing]);

  const previous = run.kind === "re-plan" ? run.previous : null;

  function download(part: PrintPart, plan?: Alternative) {
    if (!transcript) return;
    const canvas = document.querySelector<HTMLCanvasElement>(".maplibregl-canvas");
    let map: string | null = null;
    try {
      map = canvas?.toDataURL("image/png") ?? null;
    } catch {
      map = null;
    }
    setPrinting({ part, plan: plan?.key, map, file: pdfName(transcript, plan?.title ?? part, name) });
  }

  function go(next: Scenario) {
    setShowReport(false);
    start("stress test", agents, next);
  }

  function raiseBudget(budget: number) {
    const next = { ...scenario, budget };
    setScenario(next);
    start("re-plan", agents, next);
  }

  // The run plays on the map until its last beat has had its time, even once the report is in.
  const screen = run.error
    ? "error"
    : run.running || !playback.finished
      ? "running"
      : asking
        ? "asking"
        : showReport && transcript
          ? "report"
          : "setup";
  const report = screen === "report" && transcript;

  return (
    <div className="fixed inset-0 flex flex-col bg-slate-100 lg:flex-row">
      <div className={report ? "relative h-[40vh] shrink-0 lg:h-auto lg:w-[40%]" : "relative flex-1"}>
        <HazardMap
          scenario={scenario}
          quiet={screen !== "setup" && !report}
          compact={!!report}
          beat={screen === "running" ? playback.beat : null}
        />
      </div>

      {screen === "setup" && (
        <div className="pointer-events-none absolute inset-x-0 top-0 flex p-4 sm:p-5">
          <div className="pointer-events-auto w-full max-w-sm">
            <PlanSetup
              scenario={scenario}
              agents={agents}
              onScenarioChange={setScenario}
              onAgentsChange={setAgents}
              onRun={go}
              onBackToReport={transcript ? () => setShowReport(true) : null}
            />
          </div>
        </div>
      )}

      {screen === "running" && <RunStage run={run} playback={playback} onCancel={reset} />}
      {screen === "error" && (
        <RunVeil>
          <RunError error={run.error ?? ""} onBack={reset} />
        </RunVeil>
      )}
      {screen === "asking" && transcript && needed != null && (
        <RunVeil>
          <BudgetQuestion
            transcript={transcript}
            needed={needed}
            onRaise={() => raiseBudget(needed)}
            onKeep={() => setKept(transcript)}
          />
        </RunVeil>
      )}

      {report && (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <ReportHeader
            transcript={transcript}
            onDownload={download}
            hasOthers={alternatives(transcript, previous).length > 0}
            onNewPlan={() => setShowReport(false)}
          />
          <div className="px-4 pb-10 sm:px-6">
            <PlanReport
              transcript={transcript}
              previous={previous}
              onDownload={(plan) => download("plan", plan)}
            />
          </div>
        </div>
      )}

      {printing &&
        transcript &&
        createPortal(
          <div id="print-root">
            <PrintableReport
              transcript={transcript}
              previous={previous}
              part={printing.part}
              plan={printing.plan}
              map={printing.map}
            />
          </div>,
          document.body,
        )}
    </div>
  );
}

function ReportHeader({
  transcript,
  onDownload,
  hasOthers,
  onNewPlan,
}: {
  transcript: Transcript;
  onDownload: (part: PrintPart) => void;
  hasOthers: boolean;
  onNewPlan: () => void;
}) {
  const name = usePlaceName();
  const scenario = transcript.base_scenario;
  return (
    <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur sm:px-6">
      <div className="flex items-center gap-2.5">
        <Logo className="size-8" />
        <div>
          <p className="text-sm font-semibold text-slate-900">Cascade · plan report</p>
          <p className="text-xs text-slate-500">
            {scenario.scope ? name(scenario.scope) : "Whole area"} · budget{" "}
            {dollars(scenario.budget)}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {transcript.recommendation?.report && <DownloadMenu onDownload={onDownload} hasOthers={hasOthers} />}
        <button
          type="button"
          onClick={onNewPlan}
          className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-700"
        >
          New plan
        </button>
      </div>
    </header>
  );
}

function DownloadMenu({
  onDownload,
  hasOthers,
}: {
  onDownload: (part: PrintPart) => void;
  hasOthers: boolean;
}) {
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !menu.current?.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div ref={menu} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-50"
      >
        <svg viewBox="0 0 20 20" className="size-3.5" aria-hidden>
          <path
            d="M10 3v10m0 0l-4-4m4 4l4-4M4 16h12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        Download PDF
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-64 rounded-xl bg-white p-1.5 shadow-xl ring-1 ring-slate-200"
        >
          {PRINT_PARTS.filter((p) => hasOthers || p.part !== "others").map((p) => (
            <button
              key={p.part}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onDownload(p.part);
              }}
              className="block w-full rounded-lg px-3 py-2 text-left transition hover:bg-slate-50"
            >
              <span className="block text-sm font-medium text-slate-900">{p.title}</span>
              <span className="block text-xs text-slate-500">{p.detail}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Suggested file name when the browser saves the PDF, taken from the page title. */
function pdfName(transcript: Transcript, what: string, name: (id: string) => string): string {
  const scenario = transcript.base_scenario;
  const where = scenario.scope ? name(scenario.scope) : "Whole area";
  what = PRINT_PARTS.find((p) => p.part === what)?.title ?? what;
  return `Cascade - ${what} - ${where} - ${dollars(scenario.budget)}`;
}
