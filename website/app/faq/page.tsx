import type { Metadata } from "next";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

export const metadata: Metadata = {
  title: "FAQ - Obsidura",
  description:
    "Common questions about Pantheon: what it can automate, how work is triggered, how agents reach your systems, how permissions and audit logs work, and where it can be deployed.",
  alternates: {
    canonical: "/faq",
  },
};

// Rendered on the page and serialized as FAQPage structured data below -
// one source of truth so the markup never drifts from the visible copy.
const QUESTIONS = [
  {
    q: "What is Obsidura?",
    a: "Obsidura is the company. Pantheon is the product: a data layer for AI agents. It aggregates the systems your information is scattered across into one secure, governed layer and sets agents to work against it - recurring jobs on a schedule, one-off actions, whole workflows, or a question asked in plain English and answered from your data. Access is scoped to each person's role, and it escalates to a person where you say it must.",
  },
  {
    q: "What is Pantheon?",
    a: "In plain terms, one governed layer over your company's data, and a place to define, run, and manage the work that agents do against it. Underneath, a workflow orchestration engine where definitions are data, not code: your YAML compiles into a typed graph held in Postgres, a Rust executor instantiates runs from it, task bodies run in containers speaking JSON-RPC over stdio, and every resource call passes through a proxy scoped to that run.",
  },
  {
    q: "What kinds of work can it automate?",
    a: "Anything software and data can touch. A month-end performance pack, a nightly ledger reconciliation, diagnostics over rocket test telemetry checked against the standard a programme is held to, a clinical cohort summary, standing up a new network segment with a human gate on the change, matching invoices against purchase orders, or turning the office lights on. To the engine these are the same shape: a task, a permission, a check, and a record.",
  },
  {
    q: "Does it only produce reports?",
    a: "No. Reports are the example we lead with because the result is something you can see on a page, and because a report exercises the hard parts - many systems, per-person permissions, large data, a polished artifact. A job whose result is a provisioned network, a filed record, a notified person, or a switched-on light runs through exactly the same five steps.",
  },
  {
    q: "Does someone have to ask for every run?",
    a: "No. A run starts from a schedule, from another system calling in, or from a person - a button in an internal tool or a sentence typed in plain English. The definitions are identical either way; only the trigger on the front of the job differs, so a process written to be called can be put on a schedule without rewriting it.",
  },
  {
    q: "Are the AI agents doing everything?",
    a: "No, and that is deliberate. A task is either a traditional scripted task or an agent, and both run the same way. Agents are used where judgment is genuinely required - reading a mess of data and deciding what matters - while deterministic steps handle everything that should never vary, like composing the final artifact or writing a record. An agent is an ordinary task carrying extra policy, not a special execution path.",
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
    a: "Three connector kinds: Postgres, S3-compatible object storage, and HTTP. HTTP is the general case - if a system has an interface a program can call, a task can work against it through the same proxy. The v1 connector catalog - Google Workspace, Microsoft 365, Slack, Jira, Azure, NAS shares, more databases, and MCP servers - is specified and public on the connections page, and arrives in phases.",
  },
  {
    q: "How will we connect our own services?",
    a: "Through the Connections surface: pick the service, walk its consent screen or enter a credential, and the secret goes into executor custody - never into YAML, a diff, or a container. Setting up a connection is self-serve; making it reachable from a job always goes through a reviewed resource definition. Grants are then written per user in each service's own terms - a folder prefix for Drive, a channel allowlist for Slack, a JQL fragment for Jira.",
  },
  {
    q: "Are you locked to one agent framework?",
    a: "No, and it is an architectural rule rather than an intention. No framework is hardcoded at the executor level. The harness is a leaf dependency inside the runner image, so swapping it touches no engine code.",
  },
  {
    q: "Where can Pantheon run?",
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
            <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
              Frequently asked{" "}
              <span className="headline-emph">questions.</span>
            </h1>
            <p className="lede-copy mt-6 max-w-xl">
              What Pantheon can automate, how a run starts, how it touches
              your systems, and where everything runs. Something missing?
              Send word through the contact page.
            </p>

            {/* The full answers stay in the FAQPage JSON-LD above, so
                collapsing the visible copy costs nothing to search. */}
            <Accordion
              type="single"
              collapsible
              className="mt-14 divide-y divide-rule border-y border-rule"
            >
              {QUESTIONS.map(({ q, a }) => (
                <AccordionItem key={q} value={q}>
                  <AccordionTrigger>{q}</AccordionTrigger>
                  <AccordionContent>{a}</AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </section>
      </main>
    </>
  );
}
