"use client";

import { createContext, useContext, useState } from "react";

import { Num } from "@/components/EvidenceDrawer";
import Logo from "@/components/Logo";
import type {
  Action,
  Assignment,
  Candidate,
  Check,
  NeighborhoodBriefing,
  Briefing,
  PlanReport as Report,
  Recommendation,
  StressCase,
  Transcript,
} from "@/lib/api";
import { describeAction, describeAttack, describeDamage, describePlan } from "@/lib/describe";
import { dollars, join, people, percent, sentence } from "@/lib/format";
import { usePlaceName } from "@/lib/places";

/** What a PDF holds: the whole report, one part of it, or the plans not chosen. */
export type PrintPart = "full" | "field" | "backups" | "others" | "plan";

export const PRINT_PARTS: { part: PrintPart; title: string; detail: string }[] = [
  { part: "full", title: "Full plan report", detail: "Every section, with the map" },
  { part: "field", title: "Field briefing", detail: "Assignments and steps for each town" },
  { part: "backups", title: "Backup plans", detail: "What to do when something fails" },
  { part: "others", title: "Other plans", detail: "Every plan not chosen, and why" },
];

const SECTIONS_IN: Partial<Record<PrintPart, string[]>> = {
  field: ["assignments", "briefing"],
  backups: ["contingencies"],
};

/** True inside the PDF view: every case is listed and buttons are left out. */
const Printing = createContext(false);

/** Set beside the map: the stress case replaying on it, and how to replay another. */
const Replay = createContext<{ replaying: StressCase | null; onReplay: (c: StressCase) => void } | null>(
  null,
);

/** A plan that was drafted for the same conditions but not chosen. */
export type Alternative = {
  key: string;
  title: string;
  status: "Rejected" | "Not chosen" | "Earlier plan";
  reason: string;
  report: Report;
  actions: Action[];
};

/** Every plan not chosen: the plan before a budget change, then the run's other plans. */
export function alternatives(transcript: Transcript, previous: Transcript | null): Alternative[] {
  const rec = transcript.recommendation;
  const out: Alternative[] = [];
  const before = previous?.recommendation;
  if (before?.report) {
    out.push({
      key: "before",
      title: "Plan before the budget change",
      status: "Earlier plan",
      reason: `The plan for the ${dollars(before.report.scenario.budget)} budget, before you changed it.`,
      report: before.report,
      actions: before.plan.actions,
    });
  }
  const final = rec?.candidates.find((c) => c.round_index === rec.round_index);
  const rounds = transcript.rounds.filter(
    (r) => r.plan && r.report && r.plan_from_round == null && r.index !== rec?.round_index,
  );
  rounds.forEach((r, i) => {
    const failed = r.verdict?.checks.filter((c) => !c.passed) ?? [];
    const mine = rec?.candidates.find((c) => c.round_index === r.index);
    out.push({
      key: `round-${r.index}`,
      title: `Alternative ${i + 1}`,
      status: failed.length ? "Rejected" : "Not chosen",
      reason: failed.length
        ? sentence(`Rejected: ${join(failed.map(problem))}.`)
        : mine && final
          ? notChosen(mine, final)
          : "Another plan shelters more people.",
      report: r.report!,
      actions: r.plan!.actions,
    });
  });
  return out;
}

function problem(c: Check): string {
  const [claimed, actual] = [c.claimed ?? 0, c.actual ?? 0];
  switch (c.name) {
    case "budget":
      return `it is over budget (it costs ${dollars(claimed)}; the budget is ${dollars(actual)})`;
    case "cost":
      return `its cost was misstated (said ${dollars(claimed)}, really ${dollars(actual)})`;
    case "people_sheltered":
      return `it misstated how many it shelters (said ${people(claimed)}, really ${people(actual)})`;
    case "capacity":
      return `it counts ${people(claimed)} people, but its shelters hold ${people(actual)}`;
    case "places_available":
      return "it uses a shelter that is closed or does not exist";
    default:
      return c.reason || c.name.replaceAll("_", " ");
  }
}

function notChosen(mine: Candidate, final: Candidate): string {
  const close = (a: number, b: number) => Math.abs(a - b) < 0.0005;
  if (!close(mine.result.robustness, final.result.robustness)) {
    return (
      `Shelters ${people(mine.result.people_sheltered)} of ${people(mine.result.people_affected)} ` +
      `(${percent(mine.result.robustness)}); the chosen plan shelters ` +
      `${percent(final.result.robustness)}.`
    );
  }
  if (!close(mine.typical, final.typical)) {
    return (
      "Shelters as many as the chosen plan, but fewer when something fails: " +
      `${percent(mine.typical)} on average, against ${percent(final.typical)}.`
    );
  }
  const more = mine.result.cost - final.result.cost;
  return more > 0.5
    ? `Same results as the chosen plan, which costs ${dollars(more)} less.`
    : "Same results and cost as the chosen plan, which was drafted first.";
}

type Tab = "final" | "others";

/** The final plan as a report, and the plans not chosen in a second tab. */
export default function PlanReport({
  transcript,
  previous,
  onDownload,
  replaying,
  onReplay,
}: {
  transcript: Transcript;
  previous: Transcript | null;
  onDownload: (plan: Alternative) => void;
  replaying: StressCase | null;
  onReplay: (c: StressCase) => void;
}) {
  const [tab, setTab] = useState<Tab>("final");
  const others = alternatives(transcript, previous);
  return (
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white shadow-sm">
      {others.length > 0 && (
        <div role="tablist" className="flex gap-1 border-b border-slate-200 px-4 pt-3">
          <TabButton active={tab === "final"} onClick={() => setTab("final")}>
            Final plan
          </TabButton>
          <TabButton active={tab === "others"} onClick={() => setTab("others")}>
            Other plans · {others.length}
          </TabButton>
        </div>
      )}
      <div className="p-5 sm:p-7">
        {tab === "others" && others.length > 0 ? (
          <OtherPlans others={others} onDownload={onDownload} />
        ) : (
          <Replay.Provider value={{ replaying, onReplay }}>
            <FinalPlan transcript={transcript} />
          </Replay.Provider>
        )}
      </div>
    </section>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`-mb-px rounded-t-lg border-b-2 px-3 py-2 text-sm font-medium transition ${
        active
          ? "border-slate-900 text-slate-900"
          : "border-transparent text-slate-500 hover:text-slate-800"
      }`}
    >
      {children}
    </button>
  );
}

function OtherPlans({
  others,
  onDownload,
}: {
  others: Alternative[];
  onDownload: (plan: Alternative) => void;
}) {
  return (
    <div className="mx-auto max-w-4xl space-y-3">
      <p className="text-sm text-slate-600">
        The other plans drafted for these conditions, each written up in full, with why it was
        not chosen.
      </p>
      {others.map((a) => (
        <details key={a.key} className="group rounded-xl border border-slate-200">
          <summary className="flex cursor-pointer list-none items-start gap-3 p-4">
            <span className="mt-0.5 text-slate-400 transition group-open:rotate-90">▸</span>
            <span className="flex-1">
              <AlternativeHeading a={a} />
            </span>
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                onDownload(a);
              }}
              className="shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50"
            >
              PDF
            </button>
          </summary>
          <div className="border-t border-slate-100 p-4 sm:p-6">
            <Document report={a.report} />
          </div>
        </details>
      ))}
    </div>
  );
}

const STATUS_TONE: Record<Alternative["status"], string> = {
  Rejected: "bg-red-50 text-red-700 ring-red-200",
  "Not chosen": "bg-slate-100 text-slate-700 ring-slate-200",
  "Earlier plan": "bg-amber-50 text-amber-800 ring-amber-200",
};

function AlternativeHeading({ a }: { a: Alternative }) {
  const name = usePlaceName();
  const r = a.report.result;
  return (
    <>
      <span className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-900">{a.title}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${STATUS_TONE[a.status]}`}
        >
          {a.status}
        </span>
      </span>
      <span className="mt-0.5 block text-xs text-slate-500">
        {sentence(describePlan(a.actions, name))} · shelters {people(r.people_sheltered)} of{" "}
        {people(r.people_affected)} · {dollars(r.cost)}
      </span>
      <span className="mt-1 block text-sm text-slate-600">{a.reason}</span>
    </>
  );
}

/** The report laid out for printing to PDF: a letterhead, then the chosen part. */
export function PrintableReport({
  transcript,
  previous,
  part,
  plan,
  map,
}: {
  transcript: Transcript;
  previous: Transcript | null;
  part: PrintPart;
  /** The alternative's key, when one plan not chosen is printed. */
  plan?: string;
  map: string | null;
}) {
  const others = alternatives(transcript, previous);
  const printed = part === "plan" ? others.filter((a) => a.key === plan) : others;
  const title =
    part === "plan" ? printed[0]?.title : PRINT_PARTS.find((p) => p.part === part)?.title;
  return (
    <Printing.Provider value={true}>
      <div className="bg-white text-slate-900">
        <div className="mb-6 flex items-center justify-between border-b border-slate-200 pb-3">
          <span className="flex items-center gap-2">
            <Logo className="size-7" />
            <span className="text-base font-semibold tracking-tight">Cascade</span>
          </span>
          <span className="text-right text-xs text-slate-500">
            {title}
            <span className="block">
              {new Date().toLocaleDateString(undefined, { dateStyle: "long" })}
            </span>
          </span>
        </div>
        {part === "others" || part === "plan" ? (
          printed.map((a, i) => (
            <div key={a.key} className={i > 0 ? "break-before-page" : ""}>
              <div className="mb-5 rounded-lg bg-slate-50 px-4 py-3">
                <AlternativeHeading a={a} />
              </div>
              <Document report={a.report} />
            </div>
          ))
        ) : (
          <>
            {map && part === "full" && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={map}
                alt="Map of the flooded area and the shelters"
                className="mb-6 h-[105mm] w-full rounded-lg border border-slate-200 bg-slate-50 object-contain"
              />
            )}
            <FinalPlan transcript={transcript} only={SECTIONS_IN[part]} />
          </>
        )}
      </div>
    </Printing.Provider>
  );
}

function FinalPlan({ transcript, only }: { transcript: Transcript; only?: string[] }) {
  const rec = transcript.recommendation;
  if (!rec?.report) {
    return <p className="text-sm text-slate-600">No plan could be built for these conditions.</p>;
  }
  return (
    <Document
      report={rec.report}
      notice={<Shortfall rec={rec} />}
      only={only}
      extra={[
        {
          id: "contingencies",
          title: "Contingencies and backup plans",
          body: <Contingencies rec={rec} />,
        },
      ]}
    />
  );
}

/** Said up front when the plan cannot shelter everyone even when nothing goes wrong. */
function Shortfall({ rec }: { rec: Recommendation }) {
  const r = rec.result;
  if (r.people_unreached < 0.5) return null;
  return (
    <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 ring-1 ring-red-200">
      Even with nothing going wrong, this plan leaves {people(r.people_unreached)} of{" "}
      {people(r.people_affected)} affected people without a shelter.{" "}
      {rec.full_cover_cost == null
        ? "No set of the public shelters can take everyone: they lack the room or the reach."
        : `Opening shelters that take everyone costs ${dollars(rec.full_cover_cost)}, more ` +
          `than the ${dollars(rec.report?.scenario.budget ?? 0)} budget.`}
    </p>
  );
}

type Section = { id: string; title: string; body: React.ReactNode };

/** One plan report, numbered like an operations plan. */
function Document({
  report,
  notice,
  only,
  extra = [],
}: {
  report: Report;
  notice?: React.ReactNode;
  /** Section ids to keep; every section when unset. */
  only?: string[];
  extra?: Section[];
}) {
  const name = usePlaceName();
  const damage = describeDamage(report.scenario, name);
  const all: Section[] = [
    ...report.sections.map((s) => ({ id: s.title, title: s.title, body: <Lines lines={s.lines} /> })),
    {
      id: "assignments",
      title: "Organization and assignment of responsibilities",
      body: <Assignments report={report} />,
    },
    {
      id: "briefing",
      title: "Communications: field briefing",
      body: <Briefing briefing={report.briefing} report={report} />,
    },
    {
      id: "budget",
      title: "Administration, finance and logistics",
      body: <Budget report={report} />,
    },
    ...extra,
    { id: "limitations", title: "Limitations", body: <Lines lines={report.limitations} /> },
    {
      id: "references",
      title: "References",
      body: (
        <>
          <ul className="space-y-1 text-sm text-slate-700">
            {report.references.map((s) => (
              <li key={s.id}>
                <span className="mr-1.5 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                  {s.id}
                </span>
                {s.title}. <span className="text-slate-500">{s.origin}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-500">
            Format: base-plan headings from FEMA CPG 101 v3 (2021), with objectives and
            assignments in the style of ICS forms 202 and 204. Prepared by Cascade for planning
            exercises; not an official county document.
          </p>
        </>
      ),
    },
  ];
  const sections = only ? all.filter((s) => only.includes(s.id)) : all;
  return (
    <article className="mx-auto max-w-4xl">
      <header className="border-b border-slate-200 pb-4">
        <h2 className="text-xl font-semibold tracking-tight text-slate-900">{report.title}</h2>
        <p className="mt-1 text-sm text-slate-500">
          Hurricane Isaias · budget {dollars(report.scenario.budget)}
          {damage !== "no damage yet" && `; ${damage}`}
        </p>
        <KeyFigures report={report} />
        {notice}
      </header>
      <ol className="mt-5 space-y-6">
        {sections.map((s, i) => (
          <li key={s.id}>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-900 print:break-after-avoid">
              {i + 1}. {s.title}
            </h3>
            <div className="mt-2">{s.body}</div>
          </li>
        ))}
      </ol>
    </article>
  );
}

function KeyFigures({ report }: { report: Report }) {
  const { result: r, evidence: e } = report;
  const figures = [
    { label: "People affected", value: people(r.people_affected), evidence: e.people_affected },
    { label: "People sheltered", value: people(r.people_sheltered), evidence: e.people_sheltered },
    { label: "Share sheltered", value: percent(r.robustness), evidence: e.robustness },
    { label: "Cost", value: dollars(r.cost), evidence: e.cost },
    { label: "Budget", value: dollars(report.scenario.budget), evidence: e.budget },
  ];
  return (
    <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
      {figures.map((f) => (
        <div key={f.label} className="rounded-lg bg-slate-50 px-3 py-2">
          <dt className="text-[11px] uppercase tracking-wide text-slate-500">{f.label}</dt>
          <dd className="text-lg font-semibold tabular-nums text-slate-900">
            <Num label={f.label} value={f.value} evidence={f.evidence} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Lines({ lines }: { lines: string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-slate-700 marker:text-slate-400">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

const KIND_LABEL: Record<Assignment["kind"], string> = {
  shelter: "Mass care (ESF 6)",
  transport: "Transportation (ESF 1)",
  reserve: "Finance",
};

function Assignments({ report }: { report: Report }) {
  if (report.assignments.length === 0) return <Lines lines={["No assignments."]} />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-[11px] uppercase tracking-wide text-slate-500">
          <tr className="border-b border-slate-200">
            <th className="py-1.5 pr-3 font-medium">Function</th>
            <th className="py-1.5 pr-3 font-medium">Assignment</th>
            <th className="py-1.5 pr-3 font-medium">Resources</th>
            <th className="py-1.5 pr-3 font-medium">Work</th>
            <th className="py-1.5 pr-3 text-right font-medium">People</th>
            <th className="py-1.5 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {report.assignments.map((a) => (
            <tr
              key={a.title}
              className={`border-b border-slate-100 align-top ${a.funded ? "" : "text-slate-400"}`}
            >
              <td className="py-2 pr-3 text-slate-500">{KIND_LABEL[a.kind]}</td>
              <td className="py-2 pr-3 font-medium text-slate-900">
                {a.title}
                {!a.funded && (
                  <span className="ml-1.5 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                    not funded
                  </span>
                )}
              </td>
              <td className="py-2 pr-3">{a.resource}</td>
              <td className="py-2 pr-3 text-slate-600">{a.work}</td>
              <td className="py-2 pr-3 text-right tabular-nums">
                {a.people == null ? "–" : people(a.people)}
              </td>
              <td className="py-2 text-right tabular-nums">{dollars(a.cost)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Budget({ report }: { report: Report }) {
  const { result: r, evidence: e, scenario } = report;
  const left = scenario.budget - r.cost;
  return (
    <table className="w-full max-w-md text-sm">
      <tbody>
        {report.assignments.map((a) => (
          <tr key={a.title} className={a.funded ? "text-slate-700" : "text-slate-400"}>
            <td className="py-0.5 pr-3">{a.title}</td>
            <td className="py-0.5 text-right tabular-nums">{dollars(a.cost)}</td>
          </tr>
        ))}
        <tr className="border-t border-slate-200 font-medium text-slate-900">
          <td className="pt-1.5 pr-3">Total cost (reserve included)</td>
          <td className="pt-1.5 text-right tabular-nums">
            <Num label="Cost" value={dollars(r.cost)} evidence={e.cost} />
          </td>
        </tr>
        <tr className="text-slate-700">
          <td className="py-0.5 pr-3">Budget</td>
          <td className="py-0.5 text-right tabular-nums">
            <Num label="Budget" value={dollars(scenario.budget)} evidence={e.budget} />
          </td>
        </tr>
        <tr className={left < 0 ? "text-red-700" : "text-slate-700"}>
          <td className="py-0.5 pr-3">{left < 0 ? "Over budget" : "Left unspent"}</td>
          <td className="py-0.5 text-right tabular-nums">{dollars(Math.abs(left))}</td>
        </tr>
      </tbody>
    </table>
  );
}

function Briefing({ briefing, report }: { briefing: Briefing; report: Report }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(briefingText(briefing));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-slate-600">
          What staff do in each neighborhood, from this plan.
        </p>
        <button
          type="button"
          onClick={copy}
          className="shrink-0 rounded-lg px-2 py-1 text-xs text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 print:hidden"
        >
          {copied ? "Copied" : "Copy briefing"}
        </button>
      </div>
      <ul className="mt-2 grid gap-3 sm:grid-cols-2">
        {briefing.neighborhoods.map((n) => (
          <Neighborhood key={n.community_id ?? "outside"} n={n} report={report} />
        ))}
      </ul>
    </div>
  );
}

function Neighborhood({ n, report }: { n: NeighborhoodBriefing; report: Report }) {
  const e = report.evidence;
  const tags = [
    n.road_closed && "Road closed",
    n.transport_seats > 0 && `${n.transport_seats} transport seats`,
  ].filter(Boolean);
  return (
    <li className="break-inside-avoid rounded-lg border border-slate-200 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-slate-900">{n.name}</span>
        <span className="flex gap-1">
          {tags.map((t) => (
            <span
              key={String(t)}
              className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600"
            >
              {t}
            </span>
          ))}
        </span>
      </div>
      <p className="text-xs text-slate-500">
        <Num
          label={`People affected in ${n.name}`}
          value={people(n.people_affected)}
          evidence={e.people_affected}
          partOfRun
        />{" "}
        affected ·{" "}
        <Num
          label={`People sheltered in ${n.name}`}
          value={people(n.people_sheltered)}
          evidence={e.people_sheltered}
          partOfRun
        />{" "}
        sheltered
      </p>
      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs leading-relaxed text-slate-700 marker:text-slate-300">
        {n.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </li>
  );
}

/** The briefing as plain text, for pasting into a message to field staff. */
function briefingText(briefing: Briefing): string {
  const lines = ["Field briefing", briefing.conditions.join("; "), ""];
  for (const n of briefing.neighborhoods) {
    lines.push(
      `${n.name}: ${people(n.people_affected)} affected, ${people(n.people_sheltered)} sheltered`,
    );
    lines.push(...n.steps.map((s) => `- ${s}`), "");
  }
  lines.push(...briefing.limitations.map((l) => `Note: ${l}`));
  return lines.join("\n");
}

function Contingencies({ rec }: { rec: Recommendation }) {
  const name = usePlaceName();
  const cases = rec.stress?.cases ?? [];
  const singles = cases.filter((c) => c.attacks.length === 1);
  const pairs = cases.filter((c) => c.attacks.length > 1);
  const combined = rec.combined;
  const plan = rec.plan.actions;
  return (
    <div className="space-y-5 text-sm text-slate-700">
      <p>
        The plan is made for the conditions above. Below is how it holds up when things go
        wrong: each shelter it opens going offline, each affected town&apos;s road closing, and
        budget cuts of 10, 25 and 50%. Where the plan alone falls short, a backup plan says what
        to switch to if that happens.
      </p>
      {singles.length > 0 && (
        <StressGroup
          title="Small trouble: one thing fails"
          note={coverage(singles)}
          cases={singles}
          plan={plan}
        />
      )}
      {pairs.length > 0 && (
        <StressGroup
          title="Major trouble: two things fail at once"
          note={`${coverage(pairs)} Backup plans cover the ${PAIRS_WITH_BACKUP} worst.`}
          cases={pairs}
          plan={plan}
        />
      )}
      {combined && combined.attacks.length > 1 && (
        <div>
          <div className="flex items-center justify-between gap-2">
            <p className="font-medium text-slate-900">Worst case: all of these at once</p>
            <ReplayButton c={combined} />
          </div>
          <Lines lines={combined.attacks.map((a) => sentence(describeAttack(a, name)))} />
          <p className="mt-1">
            With all of them, the plan shelters {people(combined.result.people_sheltered)} of{" "}
            {people(combined.result.people_affected)} affected people (
            {percent(combined.result.robustness)}).
          </p>
          {combined.backup && <BackupLine plan={plan} c={combined} />}
        </div>
      )}
    </div>
  );
}

const WORST_SHOWN = 5;
/** Keep in sync with _PAIRS_WITH_BACKUP in loop/__init__.py. */
const PAIRS_WITH_BACKUP = 5;

function holds(c: StressCase): boolean {
  return c.result.robustness >= 0.995;
}

function holdsWithBackup(c: StressCase): boolean {
  return (c.backup?.result ?? c.result).robustness >= 0.995;
}

function coverage(cases: StressCase[]): string {
  const alone = cases.filter(holds).length;
  const backed = cases.filter(holdsWithBackup).length;
  return (
    `The plan alone still shelters everyone in ${alone} of ${cases.length} cases` +
    (backed > alone ? `; with its backup plans, in ${backed}.` : ".")
  );
}

function StressGroup({
  title,
  note,
  cases,
  plan,
}: {
  title: string;
  note: string;
  cases: StressCase[];
  plan: Action[];
}) {
  const printing = useContext(Printing);
  return (
    <div>
      <p className="font-medium text-slate-900">{title}</p>
      <p className="text-slate-600">{note}</p>
      <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {printing ? "All cases, worst first" : "Worst cases"}
      </p>
      <StressCases cases={printing ? cases : cases.slice(0, WORST_SHOWN)} plan={plan} />
      {!printing && cases.length > WORST_SHOWN && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-800">
            All {cases.length} cases
          </summary>
          <StressCases cases={cases.slice(WORST_SHOWN)} plan={plan} />
        </details>
      )}
    </div>
  );
}

function StressCases({ cases, plan }: { cases: StressCase[]; plan: Action[] }) {
  const name = usePlaceName();
  return (
    <ul className="mt-1 max-w-2xl space-y-2">
      {cases.map((c) => {
        const pct = Math.round(c.result.robustness * 100);
        const what = sentence(c.attacks.map((a) => describeAttack(a, name)).join(", and "));
        const bar = pct < 50 ? "bg-red-500" : pct < 100 ? "bg-amber-500" : "bg-emerald-500";
        return (
          <li key={what} className="break-inside-avoid text-xs text-slate-600">
            <div className="flex items-start justify-between gap-2">
              <span>{what}</span>
              <span className="flex shrink-0 items-center gap-2">
                <span className="tabular-nums">
                  {people(c.result.people_sheltered)} of {people(c.result.people_affected)} · {pct}%
                </span>
                <ReplayButton c={c} />
              </span>
            </div>
            <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-slate-100">
              <div className={`h-full rounded-full ${bar}`} style={{ width: `${pct}%` }} />
            </div>
            {c.backup && <BackupLine plan={plan} c={c} />}
          </li>
        );
      })}
    </ul>
  );
}

/** Plays the case on the map: what fails, where people go, then its backup plan. */
function ReplayButton({ c }: { c: StressCase }) {
  const replay = useContext(Replay);
  if (!replay || !c.briefing) return null;
  const playing = replay.replaying === c;
  return (
    <button
      type="button"
      onClick={() => replay.onReplay(c)}
      aria-pressed={playing}
      className={`flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium transition print:hidden ${
        playing ? "bg-sky-600 text-white" : "text-sky-700 ring-1 ring-sky-200 hover:bg-sky-50"
      }`}
    >
      <svg viewBox="0 0 12 12" className="size-2.5" aria-hidden>
        <path d="M3 1.5v9l7.5-4.5z" fill="currentColor" />
      </svg>
      {playing ? "On map" : "Show on map"}
    </button>
  );
}

/** The backup plan for a stress case, said as what changes from the plan. */
function BackupLine({ plan, c }: { plan: Action[]; c: StressCase }) {
  const name = usePlaceName();
  if (!c.backup) return null;
  const key = (a: Action) => JSON.stringify(a);
  const had = new Set(plan.map(key));
  const kept = new Set(c.backup.actions.map(key));
  const adds = c.backup.actions.filter((a) => !had.has(key(a)));
  const drops = plan.filter((a) => !kept.has(key(a)));
  const dropped = join(
    drops.map((a) => (a.type === "open_shelter" ? name(a.shelter_id) : describeAction(a, name))),
  );
  let what: string;
  if (adds.length) {
    what = sentence(describePlan(adds, name)) + (drops.length ? ` instead of ${dropped}` : "");
  } else if (drops.length) {
    what = `Skip ${dropped}`;
  } else {
    what = `Fund in this order: ${describePlan(c.backup.actions, name)}`;
  }
  const r = c.backup.result;
  return (
    <p className="mt-1 text-emerald-800">
      <span className="font-medium">Backup:</span> {what}. Shelters {people(r.people_sheltered)} of{" "}
      {people(r.people_affected)} ({percent(r.robustness)}).
    </p>
  );
}
