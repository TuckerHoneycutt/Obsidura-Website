import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "Private VPC Deployment - AWS and GCP | Obsidura",
  description:
    "Run the full Obsidura agent orchestration platform single-tenant inside your own AWS or GCP account, within your network boundary, with the same audit log and security model.",
  alternates: {
    canonical: "/deployment/private-vpc",
  },
};

export default function PrivateVpcPage() {
  return (
    <Subpage
      kicker="the dominions &mdash; private vpc"
      headlineLead="Pantheon in your"
      headlineEmph="private VPC."
      lede="Run the full orchestration platform single-tenant inside your own AWS or GCP account. Agents, runtime, and audit log all live within your network boundary - Obsidura operates the software, your cloud account holds the data."
      sections={[
        {
          heading: "What a VPC deployment gives you",
          bullets: [
            "Single-tenant: your deployment shares nothing with anyone else's.",
            "Your network boundary: connectors reach your databases and internal services over your network, not the public internet.",
            "Your cloud account: the deployment runs in AWS or GCP infrastructure you own and can inspect.",
          ],
        },
        {
          heading: "The same security model, inside your walls",
          body: [
            "Nothing about the platform relaxes in a private deployment. Task bodies still run in containers holding no credentials, reaching resources only through the run-scoped proxy. Grants are still enforced per call - a row filter for Postgres, a key prefix for object storage, a URL allowlist for HTTP - and every action still lands in the append-only run log.",
            "Contract validation at every seam, the bounded repair loop when an agent emits something malformed, durable approval gates, and crash recovery from the run log all behave identically.",
          ],
        },
        {
          heading: "When to choose VPC",
          body: [
            "Choose a private VPC when your data governance requires that operational data stay inside infrastructure you control, but you still want a managed platform rather than hardware to run. If no external calls at all is the requirement, the on-premises deployment goes further.",
          ],
        },
      ]}
      related={[
        { label: "Obsidura Cloud", href: "/deployment/cloud" },
        { label: "On-premises deployment", href: "/deployment/on-premises" },
        { label: "Security model", href: "/security" },
        { label: "Platform architecture", href: "/platform" },
      ]}
    />
  );
}
