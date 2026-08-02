import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "Obsidura Cloud - Managed AI Agent Hosting | Obsidura",
  description:
    "Run AI agents on Obsidura Cloud: fully managed agent orchestration, live in days, multi-tenant with US and EU regions - the same audit log and security model as every deployment.",
  alternates: {
    canonical: "/deployment/cloud",
  },
};

export default function CloudPage() {
  return (
    <Subpage
      kicker="the dominions &mdash; obsidura cloud"
      headlineLead="Fully managed,"
      headlineEmph="live in days."
      lede="Obsidura Cloud is the fastest way to put agents on your backend. We run the orchestration platform - the planner, the durable runtime, the audit log - and your agents connect to your systems through the same typed connectors as every other deployment."
      sections={[
        {
          heading: "What the managed cloud gives you",
          bullets: [
            "Live in days: no infrastructure to provision - connect your systems and map your first workflow.",
            "Fully managed: we operate, upgrade, and monitor the platform so your team runs workflows, not servers.",
            "US and EU regions: choose where your deployment runs to match your data residency requirements.",
          ],
        },
        {
          heading: "Multi-tenant, but your data is yours",
          body: [
            "The cloud is multi-tenant at the platform layer, and the security model does not change because of it. Agents reach your systems only through typed connectors with credentials minted per step at least privilege, executors are sandboxed with no egress beyond your declared allowlist, and every action lands in your append-only audit log.",
          ],
        },
        {
          heading: "When to choose the cloud",
          body: [
            "Choose Obsidura Cloud when you want the shortest path from a workflow on a whiteboard to an agent in production. If your data governance requires infrastructure you control, the private VPC deployment runs inside your own AWS or GCP account - and for fully isolated environments, on-premises goes all the way.",
          ],
        },
      ]}
      related={[
        { label: "Private VPC deployment", href: "/deployment/private-vpc" },
        { label: "On-premises deployment", href: "/deployment/on-premises" },
        { label: "Security model", href: "/security" },
        { label: "Platform architecture", href: "/platform" },
      ]}
    />
  );
}
