import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "AI Agents for Financial Audit | Obsidura",
  description:
    "A Pantheon pipeline that draws a ledger from Postgres, receipts from object storage, and rates from an external API, and composes them into one auditable report artifact.",
  alternates: {
    canonical: "/solutions/financial-audit",
  },
};

export default function FinancialAuditPage() {
  return (
    <Subpage
      kicker="the labors &mdash; financial audit"
      headlineLead="Agents for"
      headlineEmph="financial audit."
      lede="Audit work is exacting and scattered. The numbers live in a ledger, the evidence lives in a pile of scanned receipts, and the conversion rates live outside the company entirely. This pipeline pulls all three through one run and composes them into a single report you can hand to someone."
      sections={[
        {
          heading: "What the pipeline touches",
          bullets: [
            "A Postgres ledger, queried through the proxy under whatever row filter the requester's grant allows.",
            "Receipt documents in object storage, reached under a key prefix rather than an open bucket.",
            "An external rate API, reached over HTTP under a URL allowlist declared in the definition.",
          ],
          body: [
            "Three connector kinds in one run is the point. It is the difference between reconciling genuinely distributed data and demonstrating against a single database.",
          ],
        },
        {
          heading: "How the report gets built",
          body: [
            "An agent task gathers the permitted data and emits a structured report specification - sections, prose, dataset references, chart definitions. That output is a Record, and it is validated against its registered schema before anything downstream sees it.",
            "A deterministic render task then composes the finished site from a hand-built template and component library held as a Resource. The presentation comes from code polished once, not from a model improvising markup on the day of the meeting.",
          ],
        },
        {
          heading: "The artifact",
          body: [
            "The output is a File: a self-contained page with the data snapshot baked in, so charts render and filter in the browser with nothing running behind them. It opens like a web page because it is one.",
          ],
        },
        {
          heading: "An audit trail built for finance",
          body: [
            "Every query, every document fetched, every scope decision, and every repair attempt is an event in the run log. When a controller or an auditor asks where a figure came from, the answer is a recorded sequence rather than a reconstruction from memory.",
          ],
        },
        {
          heading: "Runs where your data has to live",
          body: [
            "Deploy in our managed cloud, in a private VPC inside your own cloud account, or on-premises with no outbound calls. Financial data can stay inside your network boundary.",
          ],
        },
      ]}
      related={[
        { label: "Flight diagnostics", href: "/solutions/flight-diagnostics" },
        { label: "Clinical summaries", href: "/solutions/clinical-summary" },
        { label: "Platform architecture", href: "/platform" },
        { label: "Security model", href: "/security" },
      ]}
    />
  );
}
