import type { Metadata } from "next";
import { MeanderMark } from "@/components/ui/meander-mark";

export const metadata: Metadata = {
  title: "FAQ - Obsidura",
  description:
    "Common questions about Obsidura: how AI agents connect to your backend, how escalation and audit logs work, and where the platform can be deployed.",
  alternates: {
    canonical: "/faq",
  },
};

// Rendered on the page and serialized as FAQPage structured data below -
// one source of truth so the markup never drifts from the visible copy.
const QUESTIONS = [
  {
    q: "What is Obsidura?",
    a: "Obsidura is an enterprise AI agent orchestration platform. Agents connect to your systems of record - databases, APIs, and business applications - execute routine operational work, and escalate to a human only when judgment is required.",
  },
  {
    q: "What is Pantheon?",
    a: "A workflow orchestration engine where definitions are data, not code. Your YAML compiles into a typed graph held in Postgres, a Rust executor instantiates runs from it, task bodies run in containers speaking JSON-RPC over stdio, and every resource call passes through a proxy scoped to that run.",
  },
  {
    q: "How do agents access our systems?",
    a: "Through a proxy. Each run gets a Unix socket mounted into its container, and that socket is the capability - the container is never handed a credential. The proxy checks the grants minted for the run, performs the call with the real credentials, writes an audit event, and returns the data.",
  },
  {
    q: "How are permissions scoped?",
    a: "A grant maps a user to a resource, the verbs they may use, and a scope in that connector's own terms: a SQL row filter for Postgres, a key prefix for object storage, a URL allowlist for HTTP. Grants are enforced on every call, so two people can ask the same question and get answers drawn from different data.",
  },
  {
    q: "What happens when a step needs a person?",
    a: "A task can gate on approval. The pending decision lives in Postgres, so the run suspends durably - restart the executor and it is still waiting - and continues when someone approves it.",
  },
  {
    q: "What stops an agent returning malformed data?",
    a: "Every task output is validated against its declared schema before anything downstream sees it. When an agent produced it, a validation failure sends a truncated error diff back to the model for a bounded number of repair attempts, then fails typed into the run log rather than passing bad data along.",
  },
  {
    q: "Is every action logged?",
    a: "Yes, and the log is not a side report. Every run is an append-only stream of events in Postgres, and executor state is a fold of that stream. Status, the audit trail, approval suspend and resume, and crash recovery all read the same table.",
  },
  {
    q: "Which systems can it connect to today?",
    a: "Three connector kinds: Postgres, S3-compatible object storage, and HTTP. HTTP is the general case - if a system has an interface a program can call, a task can work against it through the same proxy. Mail, MCP, and memory connectors are designed for and deliberately deferred.",
  },
  {
    q: "Are you locked to one agent framework?",
    a: "No, and it is an architectural rule rather than an intention. No framework is hardcoded at the executor level. The harness is a leaf dependency inside the runner image, so swapping it touches no engine code.",
  },
  {
    q: "Where can Obsidura run?",
    a: "Three deployment options: our managed cloud, a private VPC inside your own cloud account, or on-premises on your hardware with no outbound calls. The security model is the same in all three.",
  },
  {
    q: "How do we get started?",
    a: "Book a demo through the contact page. We map one of your workflows on a 30-minute call and show you the audit log by the end of it. We are currently onboarding design partners.",
  },
];

const FAQ_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: QUESTIONS.map(({ q, a }) => ({
    "@type": "Question",
    name: q,
    acceptedAnswer: { "@type": "Answer", text: a },
  })),
};

export default function FaqPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(FAQ_JSON_LD) }}
      />
      <main className="flex-1">
        <section className="relative">
          <div className="mx-auto max-w-3xl px-5 pt-16 pb-20 lg:pt-24 lg:pb-28">
            <p className="kicker mb-6 text-accent">
              appendix i &mdash; questions
            </p>
            <h1 className="font-display text-[clamp(2.5rem,5.5vw,4rem)] leading-[1.04] font-light tracking-tight">
              Frequently asked{" "}
              <span className="headline-emph">questions.</span>
            </h1>
            <p className="mt-6 max-w-xl font-mono text-sm leading-relaxed text-ink-soft">
              How the platform works, how agents touch your systems, and
              where everything runs. Something missing? Send word through
              the contact page.
            </p>

            <dl className="mt-14 divide-y divide-rule border-y border-rule">
              {QUESTIONS.map(({ q, a }) => (
                <div key={q} className="py-8">
                  <dt className="flex items-start gap-3 font-display text-2xl font-medium tracking-tight">
                    <MeanderMark size={10} className="mt-2.5 text-ink-faint" />
                    {q}
                  </dt>
                  <dd className="mt-3 pl-[22px] font-mono text-sm leading-relaxed text-ink-soft">
                    {a}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </section>
      </main>
    </>
  );
}
