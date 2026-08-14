import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "AI Agents for Clinical Summaries | Obsidura",
  description:
    "A Pantheon automation that composes patient records and scan images into a report scoped to the requester - two people, the same prompt, different reports, with every scope decision in the run log.",
  alternates: {
    canonical: "/solutions/clinical-summary",
  },
};

export default function ClinicalSummaryPage() {
  return (
    <Subpage
      kicker="a worked example &mdash; clinical summaries"
      headlineLead="Agents for"
      headlineEmph="clinical summaries."
      lede="The job that carries the governance argument, and the reason the same automation can be handed to a whole department. Patient records live in Postgres and scan images live in object storage, and what comes back depends entirely on who asked. Two people issue the same prompt; one report contains fewer patients; the log shows exactly which decisions produced the difference."
      sections={[
        {
          heading: "Permission is not a filter applied afterwards",
          body: [
            "Scope is enforced at the proxy on every call, in the terms of the connector being called - a SQL row filter for the patient records, a key prefix for the scan images. The task body never sees data the requester was not granted, so there is no later stage where something could leak through.",
            "The difference between two people's reports is therefore structural. It is not a rule someone remembered to write into a prompt, and no instruction given to a model can widen it.",
          ],
        },
        {
          heading: "What the pipeline touches",
          bullets: [
            "Patient records in Postgres, read under the row filter attached to the requester's grant.",
            "Scan images in object storage, read under a key prefix and rendered into the finished report as Files.",
          ],
        },
        {
          heading: "Every denial is an event",
          body: [
            "A scope decision that excludes something is written to the run log the same way a successful read is. That is what makes the trail useful under scrutiny: you can show not only what a report contained, but what it was prevented from containing and why.",
          ],
        },
        {
          heading: "How the report gets built",
          body: [
            "An agent task composes a structured report specification from the permitted data, and that output is validated against its registered schema before anything downstream sees it. A deterministic render task then builds the page from the template and component library.",
            "The agent's discretion is over content. The appearance is code polished once, which is why reports about entirely different subjects still come back looking like they belong to the same institution.",
          ],
        },
      ]}
      related={[
        { label: "What else Pantheon runs", href: "/automations" },
        { label: "Financial audit", href: "/solutions/financial-audit" },
        { label: "Flight diagnostics", href: "/solutions/flight-diagnostics" },
        { label: "Security model", href: "/security" },
        { label: "How workflows are built", href: "/workflows" },
      ]}
    />
  );
}
