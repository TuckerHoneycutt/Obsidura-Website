import type { Metadata } from "next";
import { Nav } from "@/components/nav";
import { Footer } from "@/components/footer";
import { romanNumeral } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Security - Obsidura",
  description:
    "How Obsidura handles credentials, sandboxing, audit logs, and deployment isolation when AI agents operate against your backend systems.",
  alternates: {
    canonical: "/security",
  },
};

const PRINCIPLES: { heading: string; body: string }[] = [
  {
    heading: "Least-privilege credentials",
    body: "Agents reach your systems only through typed connectors with scoped, audited credentials. Credentials are minted per step with the minimum privilege that step requires and revoked on completion - there is no standing god-mode key.",
  },
  {
    heading: "Sandboxed execution",
    body: "Every tool call runs in a sandboxed executor (gVisor) with per-step timeouts, retries, and idempotency keys. Executors have no network egress beyond the connector allowlist a workflow declares.",
  },
  {
    heading: "Model output is untrusted input",
    body: "The runtime treats model output the way a kernel treats userspace. Structured outputs are schema-validated at every boundary; malformed responses are repaired or retried before they touch your data.",
  },
  {
    heading: "An audit log you can replay",
    body: "Every action lands in an append-only, content-addressed audit log with the full prompt, tool call, and resulting diff. Any run can be replayed bit-for-bit against a snapshot of your data.",
  },
  {
    heading: "Humans hold the judgment calls",
    body: "When confidence drops below your threshold, the agent escalates to a human queue with the full decision trace instead of guessing. New agent versions run against shadow traffic before they ever act on production.",
  },
  {
    heading: "Deployment isolation",
    body: "Run Pantheon in our managed cloud, inside a private VPC in your own AWS or GCP account, or fully air-gapped on-premises with no external calls. Your data stays in your dominion.",
  },
];

export default function SecurityPage() {
  return (
    <>
      <Nav />
      <main className="flex-1">
        <section className="relative">
          <div className="mx-auto max-w-3xl px-5 pt-16 pb-20 lg:pt-24 lg:pb-28">
            <p className="kicker mb-6 text-accent">
              appendix iii &mdash; security
            </p>
            <h1 className="font-display text-[clamp(2.5rem,5.5vw,4rem)] leading-[1.04] font-light tracking-tight">
              Security is{" "}
              <span className="headline-emph">the architecture.</span>
            </h1>
            <p className="mt-6 max-w-xl font-mono text-sm leading-relaxed text-ink-soft">
              Obsidura asks for a connection to your systems of record, so
              the burden of proof is on us. These are the principles the
              platform is built around - not bolted on.
            </p>

            <ol className="mt-14 divide-y divide-rule border-y border-rule">
              {PRINCIPLES.map(({ heading, body }, i) => (
                <li key={heading} className="flex gap-5 py-8">
                  <span className="kicker mt-2 w-7 shrink-0 text-accent">
                    {romanNumeral(i + 1)}
                  </span>
                  <div>
                    <h2 className="font-display text-2xl font-medium tracking-tight">
                      {heading}
                    </h2>
                    <p className="mt-3 font-mono text-sm leading-relaxed text-ink-soft">
                      {body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            <p className="mt-14 border-t border-rule pt-6 font-mono text-sm leading-relaxed text-ink-mute">
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
        </section>
      </main>
      <Footer />
    </>
  );
}
