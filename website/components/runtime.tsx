import { FramePanel } from "@/components/ui/frame-panel";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { romanNumeral } from "@/lib/utils";

const GUARANTEES: string[] = [
  "Every task carries a policy - timeout, retry, budget, idempotency - and runs in a container drawn from a warm pool, so there are no cold-start delays.",
  "There are no checkpoints to fall out of sync. Executor state is a fold of the run's event log, so a killed executor rebuilds every run and finishes it.",
  "Structured outputs are schema-validated at every boundary; malformed responses are repaired or fail typed before they touch your data.",
  "Large data never travels inline. Files and tables move as handles, so a run costs the same whether it processes a hundred rows or fifty thousand.",
  "No agent framework is baked into the executor. The harness lives inside the runner image, and swapping it touches zero engine code.",
];

const MECHANISM: string[] = [
  "Task bodies speak JSON-RPC over stdio from a warm container pool, and reach resources only through a Unix socket minted for that run.",
  "Events are appended before execution; recovery folds the log rather than re-running the model.",
  "When an agent's output fails its schema, a truncated error diff goes back to the model - two attempts, then a typed failure into the run log.",
  "Every value carries an envelope: producer, causing event, taint, and budget spent. Taint is recorded today, not yet enforced.",
];

/** The body of the forge chapter. */
export function RuntimeBody() {
  return (
    <section className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <div className="grid gap-10 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
          <Reveal>
            <FramePanel className="bg-paper-warm/30">
              <div className="border-b border-rule px-5 py-2.5">
                <span className="kicker !text-[10px]">guarantees</span>
              </div>
              <ul className="divide-y divide-rule">
                {GUARANTEES.map((g, i) => (
                  <li key={g} className="flex gap-4 px-5 py-5">
                    <span className="kicker mt-1 w-7 shrink-0 text-accent">
                      {romanNumeral(i + 1)}
                    </span>
                    <p className="body-copy-sm">{g}</p>
                  </li>
                ))}
              </ul>
              <p className="body-copy-sm border-t border-rule px-5 py-4 text-ink-mute">
                Failures are surfaced immediately, never silent.
              </p>
            </FramePanel>
          </Reveal>

          <Reveal delay={0.1} className="lg:sticky lg:top-28 lg:self-start">
            <h2 className="font-display text-[clamp(1.6rem,2.4vw,2rem)] leading-tight font-light tracking-tight">
              Model output is untrusted input.
            </h2>
            <p className="body-copy mt-4">
              Nothing that comes back from a model is trusted by default.
              Every output is checked at the boundary before it is used.
            </p>

            {/* The mechanism stays in the mono voice - it is the part written
                for someone who wants the wiring, and the shift in face is
                what marks it as an aside. */}
            <div className="mt-8 border-l-2 border-accent-deep bg-paper-warm/50 px-5 py-5">
              <ul className="space-y-3">
                {MECHANISM.map((m) => (
                  <li
                    key={m}
                    className="flex gap-3 font-mono text-[12.5px] leading-relaxed text-ink-mute"
                  >
                    <span aria-hidden className="text-accent">
                      &gt;
                    </span>
                    {m}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
