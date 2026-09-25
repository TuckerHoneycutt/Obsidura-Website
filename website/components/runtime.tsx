import { CodeBlock } from "@/components/ui/code";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";

const GUARANTEES: string[] = [
  "Every task carries a policy - `timeout`, `retry`, `budget`, `idempotency` - and runs in a container drawn from a warm pool, so there are no cold-start delays.",
  "There are no checkpoints to fall out of sync. Executor state is a fold of the run's event log, so a killed executor rebuilds every run and finishes it.",
  "Structured outputs are **schema-validated at every boundary**; malformed responses are repaired or fail typed before they touch your data.",
  "Large data **never travels inline**. Files and tables move as handles, so a run costs the same whether it processes a hundred rows or fifty thousand.",
  "No agent framework is baked into the executor. The harness lives inside the runner image, and swapping it touches zero engine code.",
];

const MECHANISM: string[] = [
  "Task bodies speak `JSON-RPC` over `stdio` from a warm container pool, and reach resources only through a `Unix socket` minted for that run.",
  "Events are appended before execution; recovery folds the log rather than re-running the model.",
  "When an agent's output fails its schema, a truncated error diff goes back to the model - two attempts, then a typed failure into the run log.",
  "Every value carries an envelope: producer, causing event, `taint`, and budget spent. _Taint is recorded today, not yet enforced._",
];

/** The body of the forge chapter. */
export function RuntimeBody() {
  return (
    <section className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-shell px-gutter py-16 lg:py-20">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-16 xl:gap-20">
          <Reveal>
            <CodeBlock
              framed
              filename="GUARANTEES.md"
              lang="markdown"
              meta="what every run is owed"
              code={[
                "# Guarantees",
                "",
                ...GUARANTEES.map((g, i) => `${i + 1}. ${g}`),
                "",
                "> Failures are surfaced immediately, never silent.",
              ].join("\n")}
            />
          </Reveal>

          <Reveal delay={0.1} className="lg:sticky lg:top-28 lg:self-start">
            <h2 className="font-display max-w-xl text-[clamp(1.6rem,2.4vw,2.25rem)] leading-tight font-light tracking-tight">
              Model output is untrusted input.
            </h2>
            <p className="body-copy mt-4 max-w-xl">
              Nothing that comes back from a model is trusted by default.
              Every output is checked at the boundary before it is used.
            </p>

            {/* The mechanism, as the notes an engineer keeps next to the
                code - the part written for someone who wants the wiring. */}
            <CodeBlock
              className="mt-8"
              filename="mechanism.md"
              lang="markdown"
              status={false}
              code={["## Mechanism", "", ...MECHANISM.map((m) => `- ${m}`)].join("\n")}
            />
          </Reveal>
        </div>
      </div>
    </section>
  );
}
