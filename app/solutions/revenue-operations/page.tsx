import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "AI Agents for Revenue Operations | Obsidura",
  description:
    "Keep Salesforce clean and quote-to-cash moving with auditable AI agents - CRM hygiene, billing handoffs, and renewal monitoring with human review of every judgment call.",
  alternates: {
    canonical: "/solutions/revenue-operations",
  },
};

export default function RevenueOperationsPage() {
  return (
    <Subpage
      kicker="the labors &mdash; revenue operations"
      headlineLead="Agents for"
      headlineEmph="revenue operations."
      lede="Revenue data decays the moment nobody is looking at it. Obsidura agents do the looking - keeping your CRM honest, moving quote-to-cash handoffs along, and flagging the deals and renewals that need a human - with every field change logged."
      sections={[
        {
          heading: "The work agents take on",
          bullets: [
            "CRM hygiene in Salesforce - deduplicating records, filling gaps from your systems of record, and flagging stage changes that do not match reality.",
            "Quote-to-cash handoffs across Salesforce, NetSuite, and Stripe - carrying closed deals into billing without a human re-keying fields between systems.",
            "Renewal and account monitoring - watching dates and usage signals, preparing the routine outreach, and escalating the accounts that need attention.",
            "Routing and follow-up toil - the assignment, tasking, and nudging that keeps a pipeline moving but fills nobody's calendar by choice.",
          ],
        },
        {
          heading: "Deterministic first, judgment second",
          body: [
            "A planner decomposes each job into steps, and deterministic tools run first - matching on keys, applying your routing rules. Model calls happen only when judgment is actually required, which keeps agent behavior predictable where predictability matters.",
          ],
        },
        {
          heading: "Humans keep the judgment calls",
          body: [
            "An agent does not decide that a deal is stalled or a renewal is at risk on its own authority. Below your confidence threshold, it escalates to a human queue with the full decision trace - so your team makes the call with the evidence already assembled.",
          ],
        },
        {
          heading: "Every field change is a diff",
          body: [
            "Each update lands in an append-only audit log with the full prompt, tool call, and resulting diff. When someone asks why an opportunity moved, the answer is a replayable record, not an archaeology project.",
          ],
        },
      ]}
      related={[
        { label: "Finance operations", href: "/solutions/finance-operations" },
        { label: "Customer support", href: "/solutions/customer-support" },
        { label: "Integrations", href: "/integrations" },
        { label: "Platform architecture", href: "/platform" },
      ]}
    />
  );
}
