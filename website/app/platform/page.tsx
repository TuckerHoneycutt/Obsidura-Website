import type { Metadata } from "next";
import { Subpage } from "@/components/subpage";

export const metadata: Metadata = {
  title: "Platform - Workflow Orchestration Architecture | Obsidura",
  description:
    "How Pantheon works: YAML compiled into a typed graph, four primitives, a closed kernel of value types validated at every seam, a Rust executor over an append-only run log, and a run-scoped resource proxy.",
  alternates: {
    canonical: "/platform",
  },
};

export default function PlatformPage() {
  return (
    <Subpage
      kicker="pantheon &mdash; the architecture"
      headlineLead="The architecture"
      headlineEmph="of Pantheon."
      lede="Pantheon is a workflow orchestration engine built on one commitment: definitions are data, not code. Your YAML compiles into a typed graph held in Postgres, a Rust executor instantiates runs from it, task bodies run in containers speaking JSON-RPC over stdio, and every resource call passes through a proxy scoped to that run. Agents are ordinary tasks with extra policy, never a special execution path."
      sections={[
        {
          heading: "Four primitives",
          body: [
            "The vocabulary is deliberately small, and each primitive is a tagged union whose variant carries its own configuration. A cron trigger cannot hold a database field, because the type will not allow it.",
          ],
          bullets: [
            "Trigger - cron, webhook, or manual. Each declares the shape of the packet it produces, so the compiler can check the first link of every chain.",
            "Task - a runner plus input and output schemas, a policy covering timeout, retry, budget and idempotency, and the resources it uses. The runner is either a script or an agent.",
            "Resource - a Postgres database, an object store, or an HTTP service. It declares the verbs it exposes; secrets stay executor-side and are never handed out.",
            "Approval - a gate with approvers and a timeout. Pending approvals live in Postgres, so a suspended run survives a restart.",
          ],
        },
        {
          heading: "The kernel of values",
          body: [
            "Everything moving between tasks is one of five things: Text, a File handle, a Table handle, a Record, or an Error. The executor's duties toward them are purely operational - store and hash and gate files, meter tables, validate records against their registered schema, route errors.",
            "All business meaning lives in Records. That is what keeps the executor's size constant as your library of types grows: a domain-specific file is a File with a media type, and understanding it is a task's job at the edge, not the engine's at the centre.",
          ],
        },
        {
          heading: "Contracts at every seam",
          body: [
            "Schemas live in a registry and are referred to by name and version. Every value crossing a seam is wrapped in an envelope carrying the run, task and attempt, the schema ref, the producer, the event that caused it, its taint, and its budget spent. Large data always travels by handle, never inline.",
            "Every task output is validated against its declared output schema before anything downstream sees it. When the producer was an agent, a failure sends a truncated error diff back to the model for a bounded number of attempts, then fails typed into the run log rather than passing bad data along.",
          ],
        },
        {
          heading: "Authoring, plan, and apply",
          body: [
            "Definitions are plain YAML - one node per file or small groups, a directory as a package, references by name and version. There is no expression language and there never will be: no interpolation, no conditionals, no computation hiding inside strings. Where two shapes differ you declare a flat field-path mapping the compiler can check against both schemas, or you insert an adapter task that is honest about being computation.",
            "You never author an edge. Writing on:, then:, and uses: is enough, and the graph is derived from those references. ptn plan shows a diff against the registry and ptn apply registers it; an invalid definition is rejected at plan time, named by file, field, and rule.",
          ],
        },
        {
          heading: "The executor and the run log",
          body: [
            "The executor is Rust on tokio, with one driver per trigger kind. Its state is a fold of a single append-only table of run events - there is no separate snapshot to drift out of sync.",
            "That one table carries status queries, the audit trail, approval suspend and resume, and crash recovery. Kill the executor mid-run and it completes correctly from the log on restart.",
            "Task bodies run in a warm pool of containers speaking JSON-RPC over stdio. The shim receives an envelope, a payload, and a set of capabilities, and streams log events and the output envelope back. The agent harness exists only inside the body, so swapping it touches no executor code.",
          ],
        },
        {
          heading: "The resource proxy",
          body: [
            "Each run gets a Unix socket mounted into its container, and the socket is the capability - there is nothing to forge and nothing to escalate. Body code asks the proxy for a resource and a verb; the proxy checks the grants minted for that run, performs the call with credentials the container never sees, writes an audit event, and returns the data.",
            "Grants map a user to a resource, the verbs allowed, and a scope in that connector's own terms: a row filter for Postgres, a key prefix for object storage, a URL allowlist for HTTP. They are enforced on every call. Two people can ask the same question and receive different answers, and the log shows every scope decision that produced the difference.",
          ],
        },
      ]}
      related={[
        { label: "Security model", href: "/security" },
        { label: "Integrations", href: "/integrations" },
        { label: "Deployment options", href: "/#deploy" },
        { label: "FAQ", href: "/faq" },
      ]}
    />
  );
}
