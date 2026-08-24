import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "On-Premises and Isolated Deployment | Obsidura",
  description:
    "Run Obsidura's agent orchestration engine from containers on your own hardware with no outbound calls - built for regulated and isolated environments.",
  alternates: {
    canonical: "/deployment/on-premises",
  },
};

export default function OnPremisesPage() {
  return (
    <Subpage
      kicker="the dominions &mdash; on-premises"
      headlineLead="Isolated,"
      headlineEmph="on your hardware."
      lede="For environments where data cannot leave the building, Pantheon runs on hardware you own and makes no outbound calls. It launches from containers and needs little underneath it: a Postgres for definitions and the run log, a blob store for content, and - for the jobs that use agents at all - a model endpoint you point it at."
      art="hades"
      sections={[
        {
          heading: "What an on-premises deployment gives you",
          bullets: [
            "Your hardware: the engine runs on infrastructure you rack, image, and control.",
            "Container-based: the executor, the worker pool, and the connectors ship as containers rather than a bespoke appliance.",
            "No outbound calls: every dependency, including the model endpoint, is one you host.",
          ],
        },
        {
          heading: "Built for regulated environments",
          body: [
            "Isolation does not mean losing visibility. Every run is still an append-only stream of events in your Postgres, and executor state is still a fold of that stream - so status, the audit trail, approval suspend and resume, and crash recovery all read the same table, inside the isolated environment exactly as outside it.",
            "Approval gates work the same way behind the boundary: a task that gates on a human suspends durably, survives a restart of the executor, and continues on sign-off.",
          ],
        },
        {
          heading: "The trade to weigh",
          body: [
            "Running isolated means the model endpoint is yours to host and keep current, and whatever you can serve locally sets the ceiling on what agent tasks can accomplish. That is a real constraint rather than a footnote, and it is better examined before the posture is chosen than after.",
          ],
        },
        {
          heading: "When to choose on-premises",
          body: [
            "Choose on-premises when policy or regulation requires that no operational data cross your network edge. If you want infrastructure you control but with less to operate, the private VPC deployment runs the same engine inside your own cloud account instead.",
          ],
        },
      ]}
      related={[
        { label: "Private VPC deployment", href: "/deployment/private-vpc" },
        { label: "Obsidura Cloud", href: "/deployment/cloud" },
        { label: "Security model", href: "/security" },
        { label: "How workflows are built", href: "/workflows" },
      ]}
    />
  );
}
