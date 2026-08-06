import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "On-Premises and Air-Gapped Deployment | Obsidura",
  description:
    "Deploy Obsidura's agent orchestration platform on Kubernetes on your own hardware, fully air-gapped with no external calls - built for regulated and isolated environments.",
  alternates: {
    canonical: "/deployment/on-premises",
  },
};

export default function OnPremisesPage() {
  return (
    <Subpage
      kicker="the dominions &mdash; on-premises"
      headlineLead="Air-gapped,"
      headlineEmph="on your hardware."
      lede="For environments where data cannot leave the building, Pantheon deploys on Kubernetes on your own hardware and makes no external calls. The agents work entirely inside your walls."
      sections={[
        {
          heading: "What an on-premises deployment gives you",
          bullets: [
            "Your hardware: the platform runs on infrastructure you rack, image, and control.",
            "Kubernetes-based: deployed onto your cluster with standard tooling rather than a bespoke appliance.",
            "No external calls: fully air-gapped operation - nothing phones home.",
          ],
        },
        {
          heading: "Built for regulated environments",
          body: [
            "Isolation does not mean losing visibility. Every action still lands in the append-only, content-addressed audit log with the full prompt, tool call, and resulting diff, and any run can be replayed - which is exactly the evidence trail regulated operations need.",
            "Human-in-the-loop escalation works the same way inside the air gap: below your confidence threshold, agents stop and route to your team's queue with the full decision trace.",
          ],
        },
        {
          heading: "When to choose on-premises",
          body: [
            "Choose on-premises when policy or regulation requires that no operational data cross your network edge. If you want infrastructure you control but with less to operate, the private VPC deployment runs inside your own AWS or GCP account instead.",
          ],
        },
      ]}
      related={[
        { label: "Private VPC deployment", href: "/deployment/private-vpc" },
        { label: "Obsidura Cloud", href: "/deployment/cloud" },
        { label: "Security model", href: "/security" },
        { label: "Platform architecture", href: "/platform" },
      ]}
    />
  );
}
