"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";

import type { Evidence } from "@/lib/api";

type Opened = {
  label: string;
  value: string;
  evidence: Evidence;
  /** Set when the figure is one neighborhood's share: the inputs are for the whole run. */
  partOfRun?: boolean;
};

const OpenEvidence = createContext<(opened: Opened) => void>(() => {});

/** Lets any `Num` below it open the evidence drawer. */
export function EvidenceProvider({ children }: { children: React.ReactNode }) {
  const [opened, setOpened] = useState<Opened | null>(null);
  return (
    <OpenEvidence.Provider value={setOpened}>
      {children}
      {opened && <Drawer opened={opened} onClose={() => setOpened(null)} />}
    </OpenEvidence.Provider>
  );
}

/** A figure that opens its evidence; plain text when the run carries none for it. */
export function Num({
  label,
  value,
  evidence,
  partOfRun,
}: {
  label: string;
  value: string;
  evidence: Evidence | undefined;
  partOfRun?: boolean;
}) {
  const open = useContext(OpenEvidence);
  if (!evidence) return <>{value}</>;
  return (
    <button
      type="button"
      onClick={() => open({ label, value, evidence, partOfRun })}
      title={`Evidence for ${label.toLowerCase()}`}
      className="cursor-help rounded-sm underline decoration-current/40 decoration-dotted underline-offset-2 transition hover:decoration-current focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-current print:no-underline"
    >
      {value}
    </button>
  );
}

function Drawer({ opened, onClose }: { opened: Opened; onClose: () => void }) {
  const { label, value, evidence, partOfRun } = opened;
  const close = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      before?.focus();
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="evidence-title"
    >
      <div className="absolute inset-0 bg-slate-900/25" onClick={onClose} aria-hidden />
      <aside className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-white shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 p-4">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
              Evidence
            </p>
            <h2 id="evidence-title" className="text-base font-semibold text-slate-900">
              {label}: <span className="tabular-nums">{value}</span>
            </h2>
          </div>
          <button
            ref={close}
            type="button"
            onClick={onClose}
            className="rounded-lg px-2.5 py-1 text-sm text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50"
          >
            Close
          </button>
        </header>
        <div className="flex-1 space-y-5 overflow-y-auto p-4 text-sm leading-relaxed text-slate-700">
          <Section title="How it is computed">
            <p>{evidence.formula}</p>
          </Section>
          {evidence.inputs.length > 0 && (
            <Section
              title={partOfRun ? "This plan's numbers (all neighborhoods)" : "This plan's numbers"}
            >
              <Bullets items={evidence.inputs} />
            </Section>
          )}
          <Section title="Sources">
            <ul className="space-y-2">
              {evidence.sources.map((s) => (
                <li key={s.id}>
                  <span className="mr-1.5 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                    {s.id}
                  </span>
                  {s.title}
                  <span className="block text-xs text-slate-500">
                    {s.origin.startsWith("http") ? (
                      <a
                        href={s.origin}
                        target="_blank"
                        rel="noreferrer"
                        className="break-all underline underline-offset-2 hover:text-slate-800"
                      >
                        {s.origin}
                      </a>
                    ) : (
                      s.origin
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </Section>
          <Section title="Assumptions">
            <Bullets items={evidence.assumptions} />
          </Section>
          <Section title="Limitations">
            <Bullets items={evidence.limitations} />
          </Section>
        </div>
      </aside>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-semibold text-slate-900">{title}</h3>
      {children}
    </section>
  );
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-4 marker:text-slate-400">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}
