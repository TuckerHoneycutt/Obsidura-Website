import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "AI Agents for Finance Operations | Obsidura",
  description:
    "Put auditable AI agents on invoice matching, payment reconciliation, and close preparation - with an append-only audit trail and human review of every exception.",
  alternates: {
    canonical: "/solutions/finance-operations",
  },
};

export default function FinanceOperationsPage() {
  return (
    <Subpage
      kicker="the labors &mdash; finance operations"
      headlineLead="Agents for"
      headlineEmph="finance operations."
      lede="Finance work is exacting, repetitive, and unforgiving of errors - which makes it exactly the work agents should carry, under an audit trail your controller can actually inspect. Obsidura agents run the routine ninety percent; your team handles the judgment calls."
      sections={[
        {
          heading: "The work agents take on",
          bullets: [
            "Invoice intake and matching - reading invoices out of your systems, matching them against purchase orders and receipts, and flagging mismatches instead of guessing.",
            "Payment reconciliation across Stripe, NetSuite, and your database - tracing each transaction to its record and surfacing the ones that do not tie out.",
            "Vendor and ledger hygiene - keeping records consistent across systems, with every field change logged as a diff.",
            "Close preparation - assembling the routine checklists and reports so the humans start the close with the toil already done.",
          ],
        },
        {
          heading: "An audit trail built for finance",
          body: [
            "Every action lands in an append-only, content-addressed audit log with the full prompt, tool call, and resulting diff. When a controller or auditor asks why a record changed, you replay the run - you do not reconstruct it from memory.",
          ],
        },
        {
          heading: "Exceptions go to people",
          body: [
            "When confidence drops below your threshold - an ambiguous match, an unusual amount, a vendor that does not resolve - the agent stops and escalates to a human queue with the full decision trace attached. Nothing unusual clears without a person seeing it.",
          ],
        },
        {
          heading: "Runs where your data has to live",
          body: [
            "Deploy in our managed cloud, in a private VPC inside your own AWS or GCP account, or fully air-gapped on-premises. Financial data can stay inside your network boundary.",
          ],
        },
      ]}
      related={[
        { label: "Revenue operations", href: "/solutions/revenue-operations" },
        { label: "Platform architecture", href: "/platform" },
        { label: "Security model", href: "/security" },
        { label: "Private VPC deployment", href: "/deployment/private-vpc" },
      ]}
    />
  );
}
