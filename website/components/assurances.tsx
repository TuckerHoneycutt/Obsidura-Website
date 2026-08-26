import Link from "next/link";
import { GlowPanel } from "@/components/ui/glow-panel";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { Reveal } from "@/components/ui/reveal";

// The three objections a reasonable person raises about handing a model the
// run of their systems, answered in the order they get raised.
const CASES = [
  {
    label: "invalid model output",
    title: "It is caught and rejected.",
    plain:
      "Every result has a declared shape, and one that does not match is not passed along. The error goes back to the model to correct, twice at most, and then the run fails with a clear record of which step failed and why.",
    log: "report.spec@1 · repair 2 of 2 exhausted · typed failure written",
    href: "/security",
    linkLabel: "model output is untrusted input",
  },
  {
    label: "the machine fails mid-run",
    title: "The run resumes where it stopped.",
    plain:
      "No state lives only in the engine's memory. Every event is appended to one log and the state of a run is read back from it, so an interrupted run continues from where it stopped instead of starting over.",
    log: "executor restarted · run resumed from seq 41 · completed",
    href: "/governance",
    linkLabel: "the log it recovers from",
  },
  {
    label: "approval required",
    title: "The run waits for the decision.",
    plain:
      "A step can be gated on a human approval. The run suspends until somebody approves or denies it — surviving restarts in the meantime — and either decision is written to the same record as everything else.",
    log: "awaiting approval · 2 approvers · run suspended durably",
    href: "/governance",
    linkLabel: "the record it keeps",
  },
];

/**
 * The honest half of the pitch, in full. Anything demos well on the happy
 * path, so the forge chapter spends a section on the three ways a run goes
 * wrong - which is the part a buyer is actually weighing.
 */
export function Assurances() {
  return (
    <section className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-16 lg:py-24">
        <Reveal className="max-w-3xl">
          <p className="kicker text-accent">failure handling</p>
          <h2 className="font-display mt-6 text-[clamp(1.75rem,3.5vw,2.75rem)] leading-[1.06] font-light tracking-tight">
            What happens{" "}
            <span className="headline-emph">when a run fails.</span>
          </h2>
        </Reveal>

        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {CASES.map((c, i) => (
            <Reveal key={c.label} delay={Math.min(i * 0.07, 0.2)}>
              <GlowPanel className="h-full bg-paper-warm/30">
                <div className="flex h-full flex-col">
                  <p className="kicker border-b border-rule px-5 py-2.5 !text-[10px] text-accent">
                    {c.label}
                  </p>
                  <div className="px-5 py-5">
                    <h3 className="font-display text-[1.45rem] leading-tight font-light tracking-tight">
                      {c.title}
                    </h3>
                    <p className="body-copy-sm mt-3">{c.plain}</p>
                  </div>
                  <div className="mt-auto border-t border-rule px-5 py-4">
                    <p className="font-mono text-[11px] leading-relaxed break-words text-ink-mute">
                      {c.log}
                    </p>
                    <Link
                      href={c.href}
                      transitionTypes={["nav-forward"]}
                      className="kicker link-sweep mt-3.5 inline-block text-accent transition-colors hover:text-ink"
                    >
                      {c.linkLabel} &rarr;
                    </Link>
                  </div>
                </div>
              </GlowPanel>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
