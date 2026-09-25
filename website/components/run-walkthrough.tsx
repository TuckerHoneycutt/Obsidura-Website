import Link from "next/link";
import { FramePanel } from "@/components/ui/frame-panel";
import { BrowserBar, CodeBlock, WindowBar } from "@/components/ui/code";
import { LogLine, LogReveal } from "@/components/ui/log-reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { MiniColumns, MiniStat } from "@/components/ui/mini-chart";
import { RailNumeral } from "@/components/ui/rail-numeral";
import { Reveal } from "@/components/ui/reveal";
import { Term } from "@/components/ui/term";
import { TracingRail } from "@/components/ui/tracing-rail";

/**
 * A line of the machine's own voice. `mark` picks out the phrase that carries
 * the beat in the syntax color a terminal would give a command. Each line
 * prints in turn when its panel scrolls in.
 */
function Line({ mark, children }: { mark?: string; children: React.ReactNode }) {
  return (
    <LogLine>
      <p className="font-mono text-[0.6875rem] leading-relaxed break-words text-ink-mute">
        {mark && <span className="text-syn-key">{mark}&nbsp;&nbsp;</span>}
        {children}
      </p>
    </LogLine>
  );
}

/**
 * The system's side of a beat, in the window it would actually appear in:
 * a terminal for the run's own output, or a browser for the page a run
 * hands back.
 */
function Apparatus({
  label,
  url,
  children,
}: {
  label: string;
  url?: string;
  children: React.ReactNode;
}) {
  return (
    <FramePanel className="bg-editor" interactive={false}>
      {url ? <BrowserBar url={url} meta={label} /> : <WindowBar title={label} />}
      <LogReveal className="space-y-2 px-4 py-4">{children}</LogReveal>
    </FramePanel>
  );
}

type Step = {
  numeral: string;
  title: string;
  /** The step in words a stranger can follow. The few terms of art it
      does use carry hover-card definitions rather than inline asides. */
  plain: React.ReactNode;
  /** The same step in the system's own terms, shown rather than described. */
  panel: React.ReactNode;
};

const STEPS: Step[] = [
  {
    numeral: "i",
    title: "Something asks for the work.",
    plain:
      "A person presses a button or types what they want, a schedule comes round, or another system calls in. However it arrives, the request carries a name — because everything that happens next depends on who is asking.",
    panel: (
      <Apparatus label="the request, as it arrives">
        <Line mark="webhook">report.request</Line>
        <Line>
          prompt: &ldquo;reconcile the Q2 ledger against the receipts and flag
          anything that does not tie out&rdquo;
        </Line>
        <Line>requester: u_ellis</Line>
      </Apparatus>
    ),
  },
  {
    numeral: "ii",
    title: "The job was written down before it ran.",
    plain:
      "Which steps run, what each may touch, and the shape the answer must take are declared in plain files — reviewed like any other change, and checked for mistakes when registered, not at three in the morning.",
    panel: (
      <Apparatus label="one of the definitions, in full">
        <LogLine>
          <CodeBlock
            filename="tasks/compose_report.yaml"
            lang="yaml"
            status={false}
            code={`kind: task
name: compose_report@1
runner: agent
uses: [ledger.query, receipts.get, fx.request]
output: report.spec@1`}
          />
        </LogLine>
        <div className="space-y-2 border-t border-rule pt-3">
          <Line mark="ptn plan">3 tasks, 4 edges, no contract mismatches</Line>
          <Line mark="ptn apply">registered</Line>
        </div>
      </Apparatus>
    ),
  },
  {
    numeral: "iii",
    title: "The agent never holds the keys.",
    plain: (
      <>
        Every request for data leaves through a{" "}
        <Term t="proxy">proxy</Term> that holds the credentials. The agent
        receives rows and files; it never receives a password, and it cannot
        ask for anything the person who asked could not.
      </>
    ),
    panel: (
      <Apparatus label="what the proxy allowed, and what it refused">
        <Line mark="postgres.query">
          ledger_entries · <Term t="grant">row filter</Term>: entity =
          &lsquo;north&rsquo; · 1,284 rows
        </Line>
        <Line mark="s3.get">receipts/2026-q2/ · key prefix in scope</Line>
        <Line mark="s3.get">
          <span className="text-syn-keyword underline underline-offset-4">
            receipts/2026-q1/ denied for u_ellis
          </span>{" "}
          · decision written to the log
        </Line>
        <Line mark="http.request">fx-rates · url allowlist checked</Line>
      </Apparatus>
    ),
  },
  {
    numeral: "iv",
    title: "The answer is checked before anyone reads it.",
    plain: (
      <>
        What the agent produces has to match the{" "}
        <Term t="shape">shape declared for it</Term>{" "}
        in advance. If it does not, the mistake goes back to the model to
        correct &mdash; twice at most &mdash; and then the run stops and says
        so.
      </>
    ),
    panel: (
      <Apparatus label="the seam between one step and the next">
        <Line mark="report.spec@1">
          invalid: missing field &lsquo;findings[2].source&rsquo; · diff
          returned, attempt 1 of 2
        </Line>
        <Line mark="report.spec@1">
          valid · sealed into its <Term t="envelope">envelope</Term>
        </Line>
        <Line>
          handed to the next step with the run, the task, the attempt, and what
          it cost attached
        </Line>
      </Apparatus>
    ),
  },
  {
    numeral: "v",
    title: "Something real comes out the other end.",
    plain:
      "A last step — ordinary code, no model involved — turns the result into the thing you actually wanted. Here, a finished report; on another job, a provisioned network, a filed record, or a light that is now on.",
    panel: (
      <Apparatus
        label="what lands at the end of the run"
        url="reports/q2-ledger-reconciliation.html"
      >
        <LogLine className="pb-1">
          <p className="font-display text-[0.9375rem] leading-tight font-medium text-ink">
            Q2 Ledger Reconciliation
          </p>
          <p className="kicker mt-1.5 !text-[0.5625rem]">
            postgres · object store · http
          </p>
          <div className="mt-3.5 flex gap-5 border-t border-rule pt-3">
            <MiniStat label="entries in scope" value="1,284" />
            <MiniStat label="unmatched" value="17" />
          </div>
          <div className="mt-3.5 max-w-[300px] text-ink">
            <MiniColumns
              values={[42, 58, 35, 71, 49, 64, 53, 78]}
              labels={[
                "wk 1",
                "wk 2",
                "wk 3",
                "wk 4",
                "wk 5",
                "wk 6",
                "wk 7",
                "wk 8",
              ]}
              caption="variance by week"
              unit=" entries"
            />
          </div>
        </LogLine>
      </Apparatus>
    ),
  },
];

/**
 * The spine of the page: one run, start to finish, told twice over. The left
 * column is the account a stranger can follow; the right is the same beat in
 * the system's own voice, so the plain words can be checked against the thing
 * they describe rather than taken as marketing.
 */
export function RunWalkthrough() {
  return (
    <section className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-shell px-gutter py-16 lg:py-24">
        <Reveal className="grid max-w-3xl gap-x-16 lg:max-w-none lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:items-end">
          <div>
            <p className="kicker text-accent">one run, start to finish</p>
            <h2 className="font-display mt-6 text-[clamp(1.75rem,3.5vw,2.75rem)] leading-[1.06] font-light tracking-tight">
              How a run <span className="headline-emph">works.</span>
            </h2>
          </div>
          <p className="lede-copy mt-7 max-w-2xl lg:mt-0">
            Followed here with a request for a report, because its result is
            the one you can see on a page. On the left, what happens; on the
            right, the system saying the same thing in its own words.
          </p>
        </Reveal>

        {/* The rail threads behind the numerals; their paper patches
            interrupt it the way the meander seals interrupt a border, and
            each numeral lights as the fill passes it. */}
        <TracingRail className="mt-12">
          <ol className="border-t border-rule">
            {STEPS.map((step, i) => (
              <Reveal key={step.numeral} delay={Math.min(i * 0.05, 0.2)}>
                <li className="grid gap-8 border-b border-rule py-10 lg:grid-cols-[2.5rem_minmax(0,1fr)_minmax(0,1fr)] lg:gap-10 xl:grid-cols-[3rem_minmax(0,5fr)_minmax(0,6fr)] xl:gap-x-16">
                  <RailNumeral className="lg:relative lg:z-10 lg:self-start lg:bg-paper lg:py-2">
                    {step.numeral}
                  </RailNumeral>

                <div>
                  <h3 className="font-display text-[clamp(1.45rem,2.4vw,1.95rem)] leading-tight font-light tracking-tight">
                    {step.title}
                  </h3>
                  <p className="body-copy mt-3.5 max-w-xl">{step.plain}</p>
                </div>

                  {step.panel}
                </li>
              </Reveal>
            ))}
          </ol>
        </TracingRail>

        <Reveal delay={0.1}>
          <p className="body-copy mt-10 max-w-2xl text-ink-mute">
            Every line on the right came from the same place: a single{" "}
            <Term t="run log">append-only log</Term> of everything the run
            did. That log is the status
            page, the audit trail, and the reason a half-finished run can be
            picked back up.{" "}
            <Link
              href="/governance"
              transitionTypes={["nav-forward"]}
              className="link-sweep text-accent transition-colors hover:text-ink"
            >
              Read the log &rarr;
            </Link>
          </p>
        </Reveal>
      </div>
    </section>
  );
}
