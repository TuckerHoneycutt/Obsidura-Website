"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion, useInView, useReducedMotion } from "motion/react";
import { FramePanel } from "@/components/ui/frame-panel";
import { MiniColumns, MiniLine, MiniStat } from "@/components/ui/mini-chart";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";

type Report = {
  vertical: string;
  title: string;
  sources: string;
  stats: { label: string; value: string }[];
  chart: React.ReactNode;
  rows: string[];
  detail: string;
  href: string;
};

// The three pipelines from the spec, each drawing on a different mix of
// connectors. Figures are synthetic - the same shape as the demo fixtures.
const REPORTS: Report[] = [
  {
    vertical: "financial audit",
    title: "Q2 Ledger Reconciliation",
    sources: "postgres · object store · http",
    stats: [
      { label: "entries in scope", value: "1,284" },
      { label: "unmatched", value: "17" },
    ],
    chart: (
      <MiniColumns
        values={[42, 58, 35, 71, 49, 64, 53, 78]}
        labels={["wk 1", "wk 2", "wk 3", "wk 4", "wk 5", "wk 6", "wk 7", "wk 8"]}
        caption="variance by week"
        unit=" entries"
      />
    ),
    rows: [
      "ACC-4402   wire   $18,400   matched",
      "ACC-4419   card    $2,187   matched",
      "ACC-4460   wire    $9,050   open",
    ],
    detail:
      "A ledger, a pile of scanned receipts, and an external rate API reconciled in one run.",
    href: "/solutions/financial-audit",
  },
  {
    vertical: "flight diagnostics",
    title: "Ascent Telemetry, Test 41",
    sources: "object store · postgres",
    stats: [
      { label: "telemetry rows", value: "48,210" },
      { label: "anomalies", value: "3" },
    ],
    chart: (
      <MiniLine
        values={[18, 26, 34, 30, 47, 41, 62, 58, 74, 69, 88]}
        labels={[
          "T+0",
          "T+2s",
          "T+5s",
          "T+7s",
          "T+9s",
          "T+12s",
          "T+14s",
          "T+16s",
          "T+19s",
          "T+21s",
          "T+24s",
        ]}
        caption="chamber pressure, T+0 to T+24s"
        unit=" bar"
        flag={5}
      />
    ),
    rows: [
      "T+04.2s   chamber pressure   nominal",
      "T+11.8s   gimbal deflection   anomaly",
      "T+19.0s   stage separation   nominal",
    ],
    detail:
      "Tens of thousands of telemetry rows moved by handle, never inline, and read against the test log.",
    href: "/solutions/flight-diagnostics",
  },
  {
    vertical: "clinical summary",
    title: "Cohort Summary, Ward 3",
    sources: "postgres · object store",
    stats: [
      { label: "patients in scope", value: "36" },
      { label: "scans rendered", value: "12" },
    ],
    chart: (
      <MiniColumns
        values={[22, 38, 54, 61, 47, 33, 19]}
        labels={["18-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]}
        caption="cohort by age band"
        unit=" patients"
      />
    ),
    rows: [
      "PT-0291   intake 04-11   2 scans",
      "PT-0304   intake 04-14   1 scan",
      "PT-0318   intake 04-19   3 scans",
    ],
    detail:
      "Patient records and the scans themselves, scoped to whoever asked - two people get two different reports.",
    href: "/solutions/clinical-summary",
  },
];

// What the run reports while the artifacts are being composed. The last line
// stays on screen once the three cards have landed.
const STAGES = [
  "run opened — grants minted for u_ellis, proxy socket bound",
  "gathering — ledger, receipts, fx rates",
  "report specs valid — sealed into their envelopes",
  "3 artifacts written — self-contained, snapshots baked in",
];

const STEP_MS = 750;

function ReportCard({ report }: { report: Report }) {
  return (
    <FramePanel className="h-full bg-paper-warm/30">
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-rule px-4 py-2">
          <span className="kicker !text-[10px] text-accent">
            {report.vertical}
          </span>
          <span className="kicker !text-[10px]">html file</span>
        </div>

        {/* The artifact itself, in miniature: a titled page with figures,
            a chart, and a table - what the render task actually composes. */}
        <div className="px-4 py-5">
          <p className="font-display text-[15px] leading-tight font-medium">
            {report.title}
          </p>
          <p className="kicker mt-1.5 !text-[9px]">{report.sources}</p>

          <div className="mt-4 flex gap-5 border-t border-rule pt-3.5">
            {report.stats.map((s) => (
              <MiniStat key={s.label} label={s.label} value={s.value} />
            ))}
          </div>

          {/* Capped so a full-width card can't scale the marks into thick
              slabs - bars stay under the 24px ceiling at every breakpoint. */}
          <div className="mt-4 max-w-[310px] text-ink">{report.chart}</div>

          <div className="mt-4 space-y-1.5 border-t border-rule pt-3">
            {report.rows.map((row) => (
              <p
                key={row}
                className="truncate font-mono text-[9.5px] tracking-tight text-ink-mute tabular-nums"
              >
                {row}
              </p>
            ))}
          </div>
        </div>

        <div className="mt-auto border-t border-rule px-4 py-4">
          <p className="body-copy-sm !text-[15px] text-ink-mute">
            {report.detail}
          </p>
          {/* The link is on the link, not the whole card: wrapping an anchor
              around the chart would nest its hit targets inside an anchor. */}
          <Link
            href={report.href}
            className="kicker link-sweep mt-3 inline-block text-accent transition-colors hover:text-ink"
          >
            the full account &rarr;
          </Link>
        </div>
      </div>
    </FramePanel>
  );
}

/**
 * The body of the artifacts chapter.
 *
 * The three cards resolve one at a time behind a ticking run, because "three
 * reports materialize in their browser" is the thing being sold, and a page
 * that simply has them sitting there does not show it.
 */
export function ReportsBody() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-15% 0px" });
  const reduced = useReducedMotion();
  const [step, setStep] = useState(0);

  // A chain of timeouts rather than an interval, so the run stops ticking
  // once it has finished instead of leaving a timer on the page forever.
  useEffect(() => {
    if (!inView || reduced || step >= STAGES.length) return;
    const id = window.setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => window.clearTimeout(id);
  }, [inView, reduced, step]);

  // Reduced motion (or no observer yet) gets the finished state outright.
  const done = reduced || step >= STAGES.length;
  const stageIndex = done ? STAGES.length - 1 : Math.max(step - 1, 0);
  const shown = done ? REPORTS.length : Math.max(step - 1, 0);

  return (
    <section className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        {/* The request that starts the run, shown as the demo shell sends it. */}
        <Reveal>
          <FramePanel className="bg-paper-warm/40">
            <div className="flex items-center justify-between border-b border-rule px-4 py-2">
              <span className="kicker !text-[10px]">
                report.request &mdash; webhook trigger
              </span>
              <span className="kicker !text-[10px] text-accent">
                requester: u_ellis
              </span>
            </div>
            <p className="flex items-center gap-3 px-4 py-4 font-mono text-[13px] text-ink sm:text-sm">
              <span aria-hidden className="text-ink-faint">
                &gt;
              </span>
              Reconcile the Q2 ledger against the receipts and flag anything
              that does not tie out.
              {!done && (
                <span aria-hidden className="animate-pulse text-accent">
                  &#9608;
                </span>
              )}
            </p>
            {/* The run talking back. Deliberately not a live region: four
                announcements of a decorative sequence is noise, and the final
                line reads perfectly well on its own. */}
            <p className="border-t border-rule px-4 py-2 font-mono text-[11px] text-ink-mute">
              {STAGES[stageIndex]}
            </p>
          </FramePanel>
        </Reveal>

        <div ref={ref} className="mt-8 grid gap-6 lg:grid-cols-3">
          {REPORTS.map((report, i) => (
            <motion.div
              key={report.vertical}
              initial={false}
              animate={
                i < shown
                  ? { opacity: 1, y: 0, filter: "blur(0px)" }
                  : { opacity: 0, y: 18, filter: "blur(3px)" }
              }
              transition={{ duration: 0.5, ease: [0.21, 0.47, 0.32, 0.98] }}
              className="h-full"
            >
              <ReportCard report={report} />
            </motion.div>
          ))}
        </div>

        <Reveal delay={0.2}>
          <p className="body-copy mt-10 max-w-2xl text-ink-mute">
            Each report is a File - one self-contained page with its data
            snapshot baked in, so the charts draw and filter in the browser
            with nothing running behind them. The prose comes from an agent;
            the presentation comes from a template polished once, not from a
            model improvising markup on the morning of the meeting.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
