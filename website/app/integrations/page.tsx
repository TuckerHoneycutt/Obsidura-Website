import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "Integrations - Postgres, Object Storage, HTTP | Obsidura",
  description:
    "How Pantheon reaches your systems: Postgres, S3-compatible object storage, and HTTP services, all through a run-scoped proxy that holds the credentials and enforces per-user scope on every call.",
  alternates: {
    canonical: "/integrations",
  },
};

export default function IntegrationsPage() {
  return (
    <Subpage
      kicker="integrations"
      headlineLead="Connected to your"
      headlineEmph="systems of record."
      lede="Agents are only useful when they can act on real data. A Resource is any persistent system Pantheon can reach, and what matters is not the length of the list but the single path all of them take - no task body ever holds a credential, and every call is scoped to the person the run is acting for."
      sections={[
        {
          heading: "Three connector kinds",
          body: [
            "The engine ships with three: Postgres, S3-compatible object storage, and HTTP. Each resource declares the verbs it exposes - query, get, put, request - and the connection config it needs.",
            "Three is enough heterogeneity to make a real claim honest. One report can draw a ledger out of Postgres, receipt scans out of a bucket, and a rate from an outside API, and arrive as a single artifact.",
          ],
        },
        {
          heading: "Anything with an HTTP interface",
          body: [
            "The HTTP connector is the general case. If a system in your company has an interface a program can call, a task can work against it through the same proxy, under the same allowlist, with the same audit trail as everything else.",
            "Adding a genuinely new kind of connector is one variant on an enum plus one driver. The schema, the validation, and the authoring affordances all regenerate from the type, so the cost is bounded and known.",
          ],
        },
        {
          heading: "The credential never leaves the executor",
          body: [
            "Body code asks for a resource and a verb through a Unix socket mounted into its container for the life of that run. The socket is the capability: no token in an environment variable, no key in a config file, and nothing inside the container that can widen its own access.",
            "The proxy checks the grants minted for that run, performs the call with the real credentials, writes an audit event, and returns the data. One chokepoint doing the enforcement for every connector.",
          ],
        },
        {
          heading: "Scope is expressed per connector",
          bullets: [
            "Postgres - a SQL row filter, so a query returns only the rows the requester was granted.",
            "Object storage - a key prefix, so a bucket narrows to the part of it a person may read or write.",
            "HTTP - a URL allowlist, so a task cannot reach an endpoint the definition never declared.",
          ],
          body: [
            "Grants are enforced on every call rather than once at the start, and each decision - including each denial - lands in the run log as an event you can read afterwards.",
          ],
        },
        {
          heading: "Large data moves by handle",
          body: [
            "Values crossing a task boundary stay small. Anything large travels as a File or Table handle pointing at content in the blob store, never inline in a payload. The handle carries the capability, so holding one without the right is worth nothing.",
          ],
        },
        {
          heading: "What is not built yet",
          body: [
            "Mail connectors, MCP servers, and a memory connector are all designed for and deliberately deferred. They are not in the engine today, and we would rather say so than imply a checkbox we have not built.",
          ],
        },
      ]}
      related={[
        { label: "Platform architecture", href: "/platform" },
        { label: "Security model", href: "/security" },
        { label: "Financial audit", href: "/solutions/financial-audit" },
        { label: "Clinical summaries", href: "/solutions/clinical-summary" },
      ]}
    />
  );
}
