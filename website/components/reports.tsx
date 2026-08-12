import Link from "next/link";
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
  caption: string;
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
    chart: <MiniColumns values={[42, 58, 35, 71, 49, 64, 53, 78]} />,
    caption: "variance by week",
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
      <MiniLine values={[18, 26, 34, 30, 47, 41, 62, 58, 74, 69, 88]} flag={5} />
    ),
    caption: "chamber pressure, T+0 to T+24s",
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
    chart: <MiniColumns values={[22, 38, 54, 61, 47, 33, 19]} />,
    caption: "cohort by age band",
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

function ReportCard({ report }: { report: Report }) {
  return (
    <Link href={report.href} className="block h-full">
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
            <p className="kicker mt-1.5 !text-[9px]">{report.caption}</p>

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
            <span className="kicker link-sweep mt-3 inline-block text-accent">
              the full account &rarr;
            </span>
          </div>
        </div>
      </FramePanel>
    </Link>
  );
}

/**
 * The artifact chapter: what Pantheon actually hands back. The spec's demo
 * runs beauty first and governance second, so the reports lead and the run
 * log follows them.
 */
export function Reports() {
  return (
    <section id="reports" className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-20 lg:py-28">
        <Reveal className="max-w-2xl">
          <p className="kicker text-accent">ii &mdash; the artifacts</p>
          <h2 className="font-display mt-6 text-[clamp(2.25rem,4.5vw,3.5rem)] leading-[1.06] font-light tracking-tight">
            One prompt in.{" "}
            <span className="headline-emph">Three reports out.</span>
          </h2>
          <p className="lede-copy mt-6">
            Someone asks a question in plain language. Agents gather what that
            person is permitted to see across your databases, object stores,
            and internal APIs, and a deterministic render task composes the
            answer into a report you can open, read, and hand to someone else.
          </p>
        </Reveal>

        {/* The request that starts the run, shown as the demo shell sends it. */}
        <Reveal delay={0.1} className="mt-10">
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
              <span aria-hidden className="animate-pulse text-accent">
                &#9608;
              </span>
            </p>
          </FramePanel>
        </Reveal>

        <div className="mt-8 grid gap-6 lg:grid-cols-3">
          {REPORTS.map((report, i) => (
            <Reveal
              key={report.vertical}
              delay={0.15 + i * 0.12}
              className="h-full"
            >
              <ReportCard report={report} />
            </Reveal>
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
