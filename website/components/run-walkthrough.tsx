import Link from "next/link";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { MiniColumns, MiniStat } from "@/components/ui/mini-chart";
import { Reveal } from "@/components/ui/reveal";

/**
 * A line of the machine's own voice. `mark` promotes the phrase that carries
 * the beat to full-strength ink, since the palette is monochrome and there is
 * no colour to spend on emphasis.
 */
function Line({ mark, children }: { mark?: string; children: React.ReactNode }) {
  return (
    <p className="font-mono text-[11px] leading-relaxed break-words text-ink-mute">
      {mark && <span className="text-ink">{mark}&nbsp;&nbsp;</span>}
      {children}
    </p>
  );
}

function Apparatus({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <FramePanel className="bg-paper-warm/30" interactive={false}>
      <p className="kicker border-b border-rule px-4 py-2 !text-[10px]">
        {label}
      </p>
      <div className="space-y-2 px-4 py-4">{children}</div>
    </FramePanel>
  );
}

type Step = {
  numeral: string;
  title: string;
  /** The step in words a stranger can follow. No apparatus, no vocabulary. */
  plain: string;
  /** The same step in the system's own terms, shown rather than described. */
  panel: React.ReactNode;
};

const STEPS: Step[] = [
  {
    numeral: "i",
    title: "Something asks for the work.",
    plain:
      "A person presses a button or types what they want in plain words, a schedule comes round, or another system calls in. However it arrives, the request carries a name with it — whose request this is — because everything that happens next depends on who is asking.",
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
      "Which steps run, what data each one may touch, and the shape the answer must take are all declared in plain files. They are reviewed like any other change, and checked for mistakes when you register them — not at three in the morning when the nightly run finally trips over one.",
    panel: (
      <Apparatus label="one of the definitions, in full">
        <pre className="overflow-x-auto font-mono text-[11px] leading-relaxed whitespace-pre text-ink-soft">
          {`kind: task
name: compose_report@1
runner: agent
uses: [ledger.query, receipts.get, fx.request]
output: report.spec@1`}
        </pre>
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
    plain:
      "Every request for data leaves through a proxy that holds the credentials. It checks each call against what this particular person is permitted to see, fetches the data itself, and notes the decision. The agent receives rows and files; it never receives a password, and it cannot ask for anything the person who asked could not have asked for.",
    panel: (
      <Apparatus label="what the proxy allowed, and what it refused">
        <Line mark="postgres.query">
          ledger_entries · row filter: entity = &lsquo;north&rsquo; · 1,284 rows
        </Line>
        <Line mark="s3.get">receipts/2026-q2/ · key prefix in scope</Line>
        <Line mark="s3.get">
          <span className="text-ink underline underline-offset-4">
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
    plain:
      "What the agent produces has to match the shape declared for it in advance. If it does not, the mistake goes straight back to the model to correct — twice at most — and then the run stops and says so, rather than quietly passing something malformed down the line.",
    panel: (
      <Apparatus label="the seam between one step and the next">
        <Line mark="report.spec@1">
          invalid: missing field &lsquo;findings[2].source&rsquo; · diff
          returned, attempt 1 of 2
        </Line>
        <Line mark="report.spec@1">valid · sealed into its envelope</Line>
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
      "A last step — ordinary code, no model involved — turns the result into the thing you actually wanted. Here that is a finished report: one self-contained page of figures, charts, and tables you can open, send on, or file. On another job it is a provisioned network, a filed record, a message to the right person, or a light that is now on.",
    panel: (
      <Apparatus label="what lands at the end of the run">
        <div className="pb-1">
          <p className="font-display text-[15px] leading-tight font-medium text-ink">
            Q2 Ledger Reconciliation
          </p>
          <p className="kicker mt-1.5 !text-[9px]">
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
        </div>
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
      <div className="mx-auto max-w-6xl px-5 py-16 lg:py-24">
        <Reveal className="max-w-3xl">
          <p className="kicker text-accent">one run, start to finish</p>
          <h2 className="font-display mt-6 text-[clamp(2rem,4vw,3.15rem)] leading-[1.06] font-light tracking-tight">
            Every job, whatever it is,{" "}
            <span className="headline-emph">runs the same five ways.</span>
          </h2>
          <p className="lede-copy mt-7">
            Followed here with a request for a report, because its result is
            the one you can see on a page &mdash; but a nightly reconciliation
            and a network being provisioned pass through exactly these five
            steps. On the left, what happens. On the right, the system saying
            the same thing in its own words.
          </p>
        </Reveal>

        <ol className="mt-12 border-t border-rule">
          {STEPS.map((step, i) => (
            <Reveal key={step.numeral} delay={Math.min(i * 0.05, 0.2)}>
              <li className="grid gap-8 border-b border-rule py-10 lg:grid-cols-[2.5rem_minmax(0,1fr)_minmax(0,1fr)] lg:gap-10">
                <p className="kicker text-accent lg:pt-2">{step.numeral}</p>

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

        <Reveal delay={0.1}>
          <p className="body-copy mt-10 max-w-2xl text-ink-mute">
            Every line on the right came from the same place: a single
            append-only log of everything the run did. That log is the status
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
