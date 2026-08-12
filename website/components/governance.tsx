import { EngravedPlate } from "@/components/ui/engraved-plate";
import { FramePanel } from "@/components/ui/frame-panel";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { RunLog } from "@/components/run-log";

type Requester = {
  user: string;
  role: string;
  grants: [string, string][];
  results: [string, string][];
  note: string;
};

// The clinical pipeline, run twice. Same prompt, same definitions, two
// people - the difference comes entirely from the grants held at the proxy.
const REQUESTERS: Requester[] = [
  {
    user: "u_ellis",
    role: "attending, ward 3",
    grants: [
      ["patients · query", "row filter: ward = 3"],
      ["scans · get", "key prefix: scans/ward-3/"],
    ],
    results: [
      ["patients in report", "36"],
      ["scans rendered", "12"],
    ],
    note: "The full ward, because the grant covers the full ward.",
  },
  {
    user: "u_rhodes",
    role: "research fellow",
    grants: [
      ["patients · query", "row filter: ward = 3 and consent = 'research'"],
      ["scans · get", "no grant"],
    ],
    results: [
      ["patients in report", "12"],
      ["scans rendered", "0"],
    ],
    note: "Twenty-four patients withheld, and the report never hints at them.",
  },
];

const AUDIT: [string, string][] = [
  ["09:12:01", "grant   u_ellis    patients   query   row filter: ward = 3"],
  ["09:12:01", "scope   patients -> 36 rows in scope"],
  ["09:12:02", "grant   u_ellis    scans      get     key prefix: scans/ward-3/"],
  ["09:12:04", "grant   u_rhodes   patients   query   + consent = 'research'"],
  ["09:12:04", "scope   patients -> 12 rows in scope, 24 withheld"],
  ["09:12:05", "deny    u_rhodes   scans      get     no grant for this resource"],
];

const LOG_NOTES: string[] = [
  "Status, the audit trail, approval, and crash recovery all read this one table, so none of them can drift from each other.",
  "Kill the executor mid-run and it rebuilds every run by folding the log, then finishes the work.",
  "A task can gate on human approval. The pending decision persists, so the run survives a restart and continues when someone signs off.",
];

function RequesterCard({ requester }: { requester: Requester }) {
  return (
    <FramePanel className="h-full bg-paper-warm/30">
      <div className="flex h-full flex-col">
        <div className="flex items-baseline justify-between gap-3 border-b border-rule px-4 py-2.5">
          <span className="font-mono text-[13px] text-ink">
            {requester.user}
          </span>
          <span className="kicker !text-[9px]">{requester.role}</span>
        </div>

        <div className="px-4 py-4">
          <p className="kicker !text-[9px] text-accent">grants at the proxy</p>
          <div className="mt-2.5 space-y-2">
            {requester.grants.map(([resource, scope]) => (
              <div key={resource}>
                <p className="font-mono text-[12px] text-ink-soft">
                  {resource}
                </p>
                <p className="font-mono text-[11px] text-ink-faint">{scope}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-auto flex gap-6 border-t border-rule px-4 py-4">
          {requester.results.map(([label, value]) => (
            <div key={label}>
              <p className="kicker !text-[9px]">{label}</p>
              <p className="mt-1 font-mono text-2xl leading-none text-ink">
                {value}
              </p>
            </div>
          ))}
        </div>
        <p className="body-copy-sm border-t border-rule px-4 py-3.5 !text-[15px] text-ink-mute">
          {requester.note}
        </p>
      </div>
    </FramePanel>
  );
}

/**
 * The governance chapter. The permission beat leads because it is the one
 * claim a reader can check at a glance: same prompt, same definitions, two
 * reports. The run log follows as the evidence.
 */
export function Governance() {
  return (
    <section id="governance" className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-20 lg:py-28">
        <Reveal className="max-w-3xl">
          <p className="kicker text-accent">iv &mdash; the ledger</p>
          <h2 className="font-display mt-6 text-[clamp(2.25rem,4.5vw,3.5rem)] leading-[1.06] font-light tracking-tight">
            Two people ask the same question.{" "}
            <span className="headline-emph">
              They get different answers.
            </span>
          </h2>
          <p className="lede-copy mt-6 max-w-2xl">
            Permissions are not a filter an agent is asked politely to
            respect. Every resource call goes through a proxy holding the
            credentials, checked against the grants minted for that run, and
            the container never sees a secret at all.
          </p>
        </Reveal>

        <Reveal delay={0.1} className="mt-10">
          <FramePanel className="bg-paper-warm/40">
            <div className="flex items-center justify-between border-b border-rule px-4 py-2">
              <span className="kicker !text-[10px]">
                one prompt, issued twice
              </span>
              <span className="kicker !text-[10px] text-accent">
                clinical summary
              </span>
            </div>
            <p className="flex items-center gap-3 px-4 py-4 font-mono text-[13px] text-ink sm:text-sm">
              <span aria-hidden className="text-ink-faint">
                &gt;
              </span>
              Summarise this week&rsquo;s admissions on ward 3.
            </p>
          </FramePanel>
        </Reveal>

        <div className="mt-6 grid gap-6 sm:grid-cols-2">
          {REQUESTERS.map((requester, i) => (
            <Reveal
              key={requester.user}
              delay={0.15 + i * 0.1}
              className="h-full"
            >
              <RequesterCard requester={requester} />
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.2} className="mt-6">
          <FramePanel className="bg-paper-warm/20">
            <p className="kicker border-b border-rule px-4 py-2 !text-[10px]">
              every scope decision, written down
            </p>
            <div className="overflow-x-auto px-4 py-3.5">
              {AUDIT.map(([time, text]) => (
                <p
                  key={time + text}
                  className="flex gap-3 py-0.5 font-mono text-[11px] whitespace-pre sm:text-[12px]"
                >
                  <span className="shrink-0 text-ink-faint">[{time}]</span>
                  <span className="text-ink-soft">{text}</span>
                </p>
              ))}
            </div>
          </FramePanel>
        </Reveal>

        {/* The log itself: the table all of that was read out of. */}
        <div className="mt-16 grid gap-8 lg:grid-cols-[1.4fr_1fr] lg:gap-12">
          <Reveal>
            <RunLog />
          </Reveal>
          <Reveal delay={0.1} className="lg:pt-2">
            <h3 className="font-display text-[clamp(1.6rem,2.4vw,2rem)] leading-tight font-light tracking-tight">
              One table, folded four ways.
            </h3>
            <ul className="mt-6 space-y-4">
              {LOG_NOTES.map((note) => (
                <li key={note} className="flex gap-3">
                  <span aria-hidden className="kicker mt-1.5 text-accent">
                    &gt;
                  </span>
                  <p className="body-copy-sm text-ink-soft">{note}</p>
                </li>
              ))}
            </ul>
            {/* Athena's owl closes the column, the way the engraved plates
                close the other chapters. */}
            <div className="mt-10 hidden lg:block">
              <EngravedPlate name="athena-owl" />
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
