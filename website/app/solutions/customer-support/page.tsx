import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "AI Agents for Customer Support Operations | Obsidura",
  description:
    "Resolve routine support tickets with AI agents grounded in your real systems - orders, subscriptions, and refunds - with policy limits, human escalation, and a full audit log.",
  alternates: {
    canonical: "/solutions/customer-support",
  },
};

export default function CustomerSupportPage() {
  return (
    <Subpage
      kicker="the labors &mdash; customer support"
      headlineLead="Agents for"
      headlineEmph="support operations."
      lede="Most support volume is routine: where is my order, fix my subscription, process my refund. Obsidura agents resolve that work grounded in your actual systems of record - and hand anything unusual to your team with the full context attached."
      sections={[
        {
          heading: "The work agents take on",
          bullets: [
            "Ticket triage in Zendesk - categorizing, deduplicating, and routing so queues stay clean without a human touching every ticket.",
            "Order and subscription lookups against your database and Stripe - answering from the record, not from a guess.",
            "Refunds and account changes within the policy limits you set - anything outside them escalates instead of executing.",
            "Drafting responses grounded in the customer's actual history, ready for an agent of the human kind to send or edit.",
          ],
        },
        {
          heading: "Grounded in systems of record",
          body: [
            "This is not a chatbot improvising answers. Agents read your orders, subscriptions, and tickets through typed connectors, and structured outputs are schema-validated before they touch your data. If the record does not support an answer, the agent escalates rather than inventing one.",
          ],
        },
        {
          heading: "Escalation is the feature",
          body: [
            "When confidence drops below your threshold - an angry customer, a policy edge case, an account that does not add up - the agent stops and escalates to a human queue with the full decision trace. Your team spends its time on the conversations that need a person.",
          ],
        },
        {
          heading: "Every customer-affecting action is logged",
          body: [
            "Refunds, account changes, and messages all land in an append-only audit log with the full prompt, tool call, and resulting diff - replayable whenever you need to know exactly what happened on an account.",
          ],
        },
      ]}
      related={[
        { label: "Finance operations", href: "/solutions/finance-operations" },
        { label: "Integrations", href: "/integrations" },
        { label: "Platform architecture", href: "/platform" },
        { label: "FAQ", href: "/faq" },
      ]}
    />
  );
}
