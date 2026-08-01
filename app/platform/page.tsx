import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "Platform - AI Agent Orchestration Architecture | Obsidura",
  description:
    "How Pantheon orchestrates AI agents against your backend: typed connectors, a planning layer, a durable runtime, an append-only audit log, and human-in-the-loop escalation.",
  alternates: {
    canonical: "/platform",
  },
};

export default function PlatformPage() {
  return (
    <Subpage
      kicker="pantheon &mdash; the architecture"
      headlineLead="The architecture"
      headlineEmph="of Pantheon."
      lede="Pantheon is the orchestration layer between AI agents and your backend. It connects agents to your systems of record, runs their work as durable workflows, and records every action in an audit log you can replay. Five layers, each doing one job."
      sections={[
        {
          heading: "Typed connectors",
          body: [
            "Agents reach your systems through typed connectors - Postgres, REST, gRPC, and message queues. Connectors expose typed schemas, so a plan is validated against your actual tables and endpoints before step one runs.",
          ],
          bullets: [
            "Credentials are scoped and audited - minted per step with least privilege and revoked on completion.",
            "Executors have no network egress beyond the connector allowlist a workflow declares.",
          ],
        },
        {
          heading: "The planner",
          body: [
            "A planner decomposes each job into steps and compiles the workflow to a typed DAG before anything executes. Deterministic tools run first; model calls happen only when judgment is actually required.",
          ],
        },
        {
          heading: "The durable runtime",
          body: [
            "Workflows are durable state machines. State transitions are journaled before execution, and a crashed step resumes from its last checkpoint - never from the start.",
          ],
          bullets: [
            "Every tool call runs in a sandboxed executor with per-step timeouts, retries, and idempotency keys.",
            "Structured outputs are schema-validated at every boundary; malformed responses are repaired or retried before they touch your data.",
            "Rate limits, backpressure, and circuit breakers are enforced per connector, so a slow upstream never cascades.",
            "New agent versions run against shadow traffic before they ever act on production.",
          ],
        },
        {
          heading: "The audit log",
          body: [
            "Every action lands in an append-only, content-addressed audit log with the full prompt, tool call, and resulting diff. Any run can be replayed bit-for-bit against a snapshot of your data.",
          ],
        },
        {
          heading: "Human-in-the-loop escalation",
          body: [
            "When confidence drops below your threshold, the agent stops and escalates to a human queue with the full decision trace attached. Your team reviews exceptions, not everything.",
          ],
        },
      ]}
      related={[
        { label: "Security model", href: "/security" },
        { label: "Integrations", href: "/integrations" },
        { label: "Deployment options", href: "/#deploy" },
        { label: "FAQ", href: "/faq" },
      ]}
    />
  );
}
