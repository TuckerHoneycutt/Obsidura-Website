import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { RunLog } from "@/components/run-log";
import { ScopeTrace } from "@/components/scope-trace";

const LOG_NOTES: string[] = [
  "Status, the audit trail, approval, and crash recovery all read from this one table, so they always agree.",
  "If the executor is killed mid-run, it rebuilds each run's state from the log and finishes the work.",
  "A task can gate on human approval. The pending decision persists, so the run survives a restart and continues when someone signs off.",
];

/**
 * The governance chapter. The permission beat leads because it is the one
 * claim a reader can check at a glance: same prompt, same definitions, two
 * answers, played side by side so the reader watches where they split.
 * The run log follows as the evidence.
 */
export function GovernanceBody() {
  return (
    <section className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-shell px-gutter py-16 lg:py-20">
        <Reveal>
          <ScopeTrace />
        </Reveal>

        {/* The log itself: the table all of that was read out of. */}
        <div className="mt-16 grid gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-12 xl:gap-20">
          <Reveal>
            <RunLog />
          </Reveal>
          <Reveal delay={0.1} className="lg:pt-2">
            <h3 className="font-display text-[clamp(1.6rem,2.4vw,2rem)] leading-tight font-light tracking-tight">
              One table, four uses.
            </h3>
            <ul className="mt-6 max-w-xl space-y-4">
              {LOG_NOTES.map((note) => (
                <li key={note} className="flex gap-3">
                  <span aria-hidden className="kicker mt-1.5 text-accent">
                    &gt;
                  </span>
                  <p className="body-copy-sm text-ink-soft">{note}</p>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
