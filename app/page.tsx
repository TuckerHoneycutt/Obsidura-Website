import { Nav } from "@/components/nav";
import { Hero } from "@/components/hero";
import { AgentRun } from "@/components/agent-run";
import { SectionRail } from "@/components/section-rail";
import { Integrations } from "@/components/integrations";
import {
  FeatureSection,
  type FeatureContent,
} from "@/components/feature-section";
import { Deploy } from "@/components/deploy";
import { Footer } from "@/components/footer";

const PLATFORM: FeatureContent = {
  id: "platform",
  kicker: "yggdrasil - the roots",
  headlineLead: "Orchestration from",
  headlineEmph: "the roots up.",
  lede:
    "Yggdrasil's roots reach into your systems of record, and a workflow only involves a human when it has to. Agents do the routine ninety percent; your team handles the judgment calls.",
  bullets: [
    "Agents mount your backend through typed connectors - Postgres, REST, gRPC, message queues - with scoped, audited credentials.",
    "A planner decomposes each job into steps. Deterministic tools run first; model calls happen only when judgment is actually required.",
    "Every action lands in an append-only audit log with the full prompt, tool call, and resulting diff - replayable at any time.",
    "When confidence drops below your threshold, the agent escalates to a human queue with full context instead of guessing.",
  ],
  closer: "Humans review exceptions, not everything.",
  nerdLede:
    "Under the hood, each workflow compiles to a typed DAG before anything executes:",
  nerdBullets: [
    "Connectors expose typed schemas, so a plan is validated against your actual tables and endpoints before step one runs.",
    "Tool calls carry least-privilege credentials minted per step and revoked on completion.",
    "The audit log is content-addressed; any run can be replayed bit-for-bit against a snapshot of your data.",
    "Escalations carry the full decision trace, so a human resolves them in seconds, not by re-deriving context.",
  ],
  figure: "fig. 02",
};

const RUNTIME: FeatureContent = {
  id: "runtime",
  kicker: "yggdrasil - the trunk",
  headlineLead: "Automation shouldn't",
  headlineEmph: "feel fragile.",
  lede:
    "The reliability lives in the runtime. We engineer the orchestration layer like an operating system, not a chatbot - so agents keep working when models misbehave and upstreams slow down.",
  bullets: [
    "Every tool call runs in a sandboxed executor with per-step timeouts, retries, and idempotency keys.",
    "Workflows are durable state machines: a crashed step resumes from its last checkpoint, never from the start.",
    "Structured outputs are schema-validated at every boundary; malformed responses are repaired or retried before they touch your data.",
    "Rate limits, backpressure, and circuit breakers are enforced per connector, so a slow upstream never cascades.",
    "New agent versions run against shadow traffic before they ever act on production.",
  ],
  closer: "The agents spend their time working, not failing quietly.",
  nerdLede:
    "The runtime treats model output as untrusted input, the same way a kernel treats userspace:",
  nerdBullets: [
    "Executors are gVisor-sandboxed with no network egress beyond the declared connector allowlist.",
    "State transitions are journaled before execution; recovery replays the journal, not the model.",
    "Schema repair is a constrained decode against the target type - no free-form retries.",
    "Shadow runs diff their would-be writes against production behavior and gate promotion on the delta.",
  ],
  figure: "fig. 03",
  reverse: true,
};

export default function Home() {
  return (
    <>
      <Nav />
      <SectionRail />
      <main>
        <Hero />
        <Integrations />
        <AgentRun />
        <FeatureSection content={PLATFORM} />
        <FeatureSection content={RUNTIME} />
        <Deploy />
      </main>
      <Footer />
    </>
  );
}
