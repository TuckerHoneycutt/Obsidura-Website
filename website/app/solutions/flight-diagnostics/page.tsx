import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "AI Agents for Flight Diagnostics | Obsidura",
  description:
    "A Pantheon automation that reads tens of thousands of telemetry rows out of object storage as a Table handle, joins them against test and anomaly logs in Postgres, and renders a diagnostics report when a test run finishes.",
  alternates: {
    canonical: "/solutions/flight-diagnostics",
  },
};

export default function FlightDiagnosticsPage() {
  return (
    <Subpage
      kicker="a worked example &mdash; flight diagnostics"
      headlineLead="Agents for"
      headlineEmph="flight diagnostics."
      lede="Telemetry is the case that breaks naive plumbing. A single test produces far more data than anything should put inside a message payload, and the useful answer is a handful of charts, a short list of anomalies, and a check against the standard the programme is held to. This job runs itself when a test finishes, and it is the one that proves values stay small while data stays large."
      sections={[
        {
          heading: "What the pipeline touches",
          bullets: [
            "Telemetry exports in object storage - tens of thousands of rows, carried as a Table handle rather than inlined into any payload.",
            "Test and anomaly logs in Postgres, joined against the telemetry to give the numbers their context.",
          ],
        },
        {
          heading: "Why handles matter here",
          body: [
            "Values that cross a task boundary stay small. Anything large travels as a File or Table handle pointing at content in the blob store, and the handle carries the capability - holding one without the right to use it is worth nothing.",
            "That single rule keeps a run cheap regardless of how much data it reasons about. The executor's duty toward a Table is to meter it, not to carry it.",
          ],
        },
        {
          heading: "How the report gets built",
          body: [
            "An agent task decides what is worth showing - which series, which windows, which anomalies deserve prose - and emits that as a structured report specification validated against its registered schema.",
            "A deterministic render task composes the page from the template and component library. Charts render and filter client-side against a snapshot baked into the artifact, so the page feels live without anything running behind it.",
          ],
        },
        {
          heading: "Reproducible, not just repeatable",
          body: [
            "The run is a stream of events: which export was read, which rows were in scope, what the agent proposed, what failed validation and was repaired, what the renderer produced. Two people looking at the same report trace it back to the same recorded history.",
          ],
        },
      ]}
      related={[
        { label: "What else Pantheon runs", href: "/automations" },
        { label: "Financial audit", href: "/solutions/financial-audit" },
        { label: "Clinical summaries", href: "/solutions/clinical-summary" },
        { label: "How workflows are built", href: "/workflows" },
        { label: "Integrations", href: "/integrations" },
      ]}
    />
  );
}
