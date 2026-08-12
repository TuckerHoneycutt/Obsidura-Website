import { Hero } from "@/components/hero";
import { SectionRail } from "@/components/section-rail";
import { Integrations } from "@/components/integrations";
import { Reports } from "@/components/reports";
import { Definition } from "@/components/definition";
import { Governance } from "@/components/governance";
import {
  FeatureSection,
  type FeatureContent,
} from "@/components/feature-section";
import { Deploy } from "@/components/deploy";
import { Interlude } from "@/components/interlude";

const RUNTIME: FeatureContent = {
  id: "runtime",
  kicker: "v - the forge",
  headlineLead: "Automation shouldn't",
  headlineEmph: "feel fragile.",
  lede:
    "The reliability is forged in the runtime. We engineer the orchestration layer the way Hephaestus forged armor for the gods - like an operating system, not a chatbot - so agents keep working when models misbehave and upstreams slow down.",
  bullets: [
    "Every task carries a policy - timeout, retry, budget, idempotency - and runs in a container drawn from a warm pool, so cold starts never show.",
    "There are no checkpoints to fall out of sync. Executor state is a fold of the run's event log, so a killed executor rebuilds every run and finishes it.",
    "Structured outputs are schema-validated at every boundary; malformed responses are repaired or fail typed before they touch your data.",
    "Large data never travels inline. Files and tables move as handles, so a run costs the same whether it reasons over a hundred rows or fifty thousand.",
    "No agent framework is baked into the executor. The harness lives inside the runner image, and swapping it touches zero engine code.",
  ],
  closer: "The agents spend their time working, not failing quietly.",
  art: "hephaestus",
  nerdLede:
    "The runtime treats model output as untrusted input, the same way a kernel treats userspace:",
  nerdBullets: [
    "Task bodies speak JSON-RPC over stdio from a warm container pool, and reach resources only through a Unix socket minted for that run.",
    "Events are appended before execution; recovery folds the log rather than re-running the model.",
    "When an agent's output fails its schema, a truncated error diff goes back to the model - two attempts, then a typed failure into the run log.",
    "Every value carries an envelope: producer, causing event, taint, and budget spent. Taint is recorded today, not yet enforced.",
  ],
  reverse: true,
};

/**
 * The homepage runs in the order the product demo does: the artifact first,
 * then how it was authored, then how it was governed, then why it holds and
 * where it runs. Beauty before governance, per the spec's own demo script.
 */
export default function Home() {
  return (
    <>
      <SectionRail />
      <main>
        <Hero />
        <Integrations />
        <Reports />
        <Definition />
        <Governance />
        <Interlude />
        <FeatureSection content={RUNTIME} />
        <Deploy />
      </main>
    </>
  );
}
