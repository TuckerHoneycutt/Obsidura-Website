import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "Integrations - Postgres, Salesforce, Slack, Stripe, AWS | Obsidura",
  description:
    "Obsidura agents work through typed connectors into the systems you already run: Postgres, Salesforce, Slack, Stripe, AWS, Snowflake, Zendesk, NetSuite, Kafka, GitHub, Jira, and Workday.",
  alternates: {
    canonical: "/integrations",
  },
};

export default function IntegrationsPage() {
  return (
    <Subpage
      kicker="the agora &mdash; connects to"
      headlineLead="Connected to your"
      headlineEmph="systems of record."
      lede="Agents are only useful when they can act on real data. Obsidura connects to the systems you already run through typed connectors - so an agent reads your actual orders, invoices, and tickets, not a stale export."
      sections={[
        {
          heading: "Databases and warehouses",
          body: [
            "Agents query and write through connectors for Postgres and Snowflake. Connectors expose typed schemas, so a workflow is validated against your actual tables before it runs.",
          ],
        },
        {
          heading: "Business applications",
          body: [
            "Connectors for Salesforce, NetSuite, Workday, Zendesk, Jira, and GitHub let agents work inside the tools your teams live in - reading records, updating fields, filing and resolving items.",
          ],
        },
        {
          heading: "Messaging, events, and infrastructure",
          body: [
            "Slack for notifications and human escalation, Kafka for event streams, Stripe for payments data, and AWS for infrastructure - all through the same connector model.",
          ],
        },
        {
          heading: "Anything with an API",
          body: [
            "Beyond the named integrations, agents mount your backend through generic typed connectors for REST, gRPC, and message queues. If your internal service has an interface, an agent can work against it.",
          ],
        },
        {
          heading: "How every connector behaves",
          bullets: [
            "Credentials are scoped and audited - minted per step with least privilege and revoked on completion.",
            "Executors have no network egress beyond the connector allowlist a workflow declares.",
            "Every read and write lands in the append-only audit log with the full context that produced it.",
          ],
        },
      ]}
      related={[
        { label: "Platform architecture", href: "/platform" },
        { label: "Security model", href: "/security" },
        { label: "Finance operations", href: "/solutions/finance-operations" },
        { label: "Customer support", href: "/solutions/customer-support" },
      ]}
    />
  );
}
