import type { Metadata } from "next";
import { romanNumeral } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Security - Obsidura",
  description:
    "The principles Obsidura is built around: credentials stay in platform custody, access follows the person, humans gate what matters, and every run is recorded.",
  alternates: {
    canonical: "/security",
  },
};

// The posture without the blueprints: each principle states a promise the
// platform enforces, never the mechanism that enforces it. The engine's
// internals stay off the public site.
const PRINCIPLES: { heading: string; body: string }[] = [
  {
    heading: "Your tools never hold a credential",
    body: "Code running on the platform is never handed a secret. The platform holds the credentials, makes each call on the tool's behalf, and hands back only the data - so there is no token to leak and no way for code to widen its own access.",
  },
  {
    heading: "Access follows the person",
    body: "What a tool or agent may reach is scoped to the role of whoever it is working for, and the check happens on every call rather than once at the start. Two people can use the same tool and each only ever touches what they are allowed to touch.",
  },
  {
    heading: "Model output is untrusted input",
    body: "Nothing an agent produces is passed along on faith. Output is checked before anything downstream sees it, and work that fails the check is stopped and recorded rather than waved through.",
  },
  {
    heading: "Security is enforced, not prompted",
    body: "No agent is asked to be careful. What it may touch, what its output must satisfy, and what it may spend are rules the platform enforces - not instructions the model is trusted to follow.",
  },
  {
    heading: "Humans gate what matters",
    body: "Any step can require a person's approval before it proceeds. The work waits - durably, through restarts - until someone decides, and the decision is part of the record.",
  },
  {
    heading: "Every run is recorded",
    body: "What ran, for whom, what it touched, and what it produced is written down as it happens. The audit trail is not a side report that can drift from what happened - it is what happened.",
  },
];

export default function SecurityPage() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
        <section className="relative">
          <div className="mx-auto max-w-3xl px-5 pt-16 pb-20 lg:pt-24 lg:pb-28">
            <p className="kicker mb-6 text-accent">
              appendix iii &mdash; security
            </p>
            <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
              The security <span className="headline-emph">model.</span>
            </h1>
            <p className="lede-copy mt-6 max-w-xl">
              Pantheon asks to run work against your systems, much of it
              while nobody is watching, so the burden of proof is on us.
              These are the principles the platform is built around - not
              bolted on.
            </p>

            <ol className="mt-14 divide-y divide-rule border-y border-rule">
              {PRINCIPLES.map(({ heading, body }, i) => (
                <li key={heading} className="flex gap-5 py-8">
                  <span className="kicker mt-2 w-7 shrink-0 text-accent">
                    {romanNumeral(i + 1)}
                  </span>
                  <div>
                    <h2 className="font-display text-[1.75rem] font-medium tracking-tight">
                      {heading}
                    </h2>
                    <p className="body-copy mt-3">
                      {body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            <p className="body-copy mt-14 border-t border-rule pt-6 text-ink-mute">
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
  );
}
