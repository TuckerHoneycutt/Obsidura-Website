import type { Metadata } from "next";
import { cn, romanNumeral } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Security - Obsidura",
  description:
    "How Obsidura handles credentials, sandboxing, audit logs, and deployment isolation when automations - agents and scripts alike - run against your systems, scheduled or on demand.",
  alternates: {
    canonical: "/security",
  },
};

const PRINCIPLES: { heading: string; body: string }[] = [
  {
    heading: "The container never holds a credential",
    body: "A task body reaches a resource through a Unix socket mounted into its container for the lifetime of one run. The socket is the capability. There is no token in an environment variable to leak and no way for code inside to widen its own access - the executor makes the call with the real credentials and hands back only the data.",
  },
  {
    heading: "One chokepoint, written in Rust",
    body: "Because every resource call goes through the proxy, capability enforcement, budget metering, and audit logging happen in one place rather than scattered through task code. The trusted surface stays small and auditable while the task body remains free to use whatever library it needs.",
  },
  {
    heading: "Access follows the person",
    body: "Grants map a user to a resource, the verbs allowed, and a scope in that connector's own terms - a SQL row filter, an object-storage key prefix, an HTTP URL allowlist. They are checked on every call rather than once at the start, so two people asking the same question receive answers drawn from different data, and the log shows every scope decision that made the difference.",
  },
  {
    heading: "Model output is untrusted input",
    body: "The runtime treats model output the way a kernel treats userspace. Every task output is validated against its declared schema before anything downstream sees it. When an agent produced it, a failure sends a truncated error diff back to the model for a bounded number of repair attempts, then fails typed into the run log rather than passing malformed data along.",
  },
  {
    heading: "Security decisions are structural, not prompted",
    body: "No agent is asked to be careful. An agent is an ordinary task carrying extra policy, and the rules that matter - which resources it may touch, what its output must satisfy, what it may spend - are properties of the definition the executor enforces. Because the definition graph is data rather than code, which task can reach which resource is a question you answer by reading.",
  },
  {
    heading: "Provenance travels with the data",
    body: "Every value crossing a seam carries an envelope: the run, task and attempt that produced it, the schema it satisfies, the event that caused it, its taint, and its budget spent. Taint is recorded and logged today but not yet enforced - carrying it from the start is what makes enforcing it later a policy change rather than a migration.",
  },
  {
    heading: "Approvals suspend durably",
    body: "A task can gate on human approval. The pending decision lives in Postgres, so restarting the executor leaves the run exactly where it was, waiting, and approving it lets the run continue. Suspension that survives a restart is the difference between a real gate and a polling loop.",
  },
  {
    heading: "The run log is the evidence",
    body: "Every run is an append-only stream of events, and executor state is a fold of that stream. Status queries, the audit trail, approval resume, and crash recovery all read the same table - so the audit trail is not a side report that can drift from what happened. It is what happened.",
  },
];

// Numeral and heading on the left, the principle on the right at lg.
const ROW =
  "grid gap-y-3 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-x-[clamp(3rem,6vw,6rem)]";

export default function SecurityPage() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <section className="relative">
        {/* Wide frame, reading-measure prose: the title and each principle
            hold the left column, the argument runs on the right. */}
        <div className="mx-auto max-w-shell px-gutter pt-16 pb-20 lg:pt-24 lg:pb-28">
          <div className="grid gap-y-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-x-[clamp(3rem,6vw,6rem)]">
            <div>
              <p className="kicker mb-6 text-accent">
                appendix iii &mdash; security
              </p>
              <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
                The security <span className="headline-emph">model.</span>
              </h1>
            </div>
            <p className="lede-copy max-w-xl lg:self-end">
              Pantheon asks to run work against your systems, much of it
              while nobody is watching, so the burden of proof is on us.
              These are the principles the platform is built around - not
              bolted on. Where something is recorded today but not yet
              enforced, it says so.
            </p>
          </div>

          <ol className="mt-14 divide-y divide-rule border-y border-rule lg:mt-20">
            {PRINCIPLES.map(({ heading, body }, i) => (
              <li key={heading} className={cn(ROW, "py-8")}>
                <div className="flex gap-5">
                  <span className="kicker mt-2 w-7 shrink-0 text-accent">
                    {romanNumeral(i + 1)}
                  </span>
                  <h2 className="font-display text-[1.75rem] font-medium tracking-tight">
                    {heading}
                  </h2>
                </div>
                {/* Indented under the heading when stacked, so the numeral
                    keeps its own margin; beside it once there is room. */}
                <p className="body-copy max-w-2xl pl-12 lg:pl-0">{body}</p>
              </li>
            ))}
          </ol>

          <div className={cn(ROW, "mt-14 border-t border-rule pt-6")}>
            <p className="body-copy max-w-2xl text-ink-mute lg:col-start-2">
              Found a vulnerability in this site or our platform? Email{" "}
              <a
                href="mailto:contact@obsidura.com"
                className="text-ink underline underline-offset-4"
              >
                contact@obsidura.com
              </a>{" "}
              and we will respond promptly. We ask for reasonable time to
              remediate before public disclosure.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
