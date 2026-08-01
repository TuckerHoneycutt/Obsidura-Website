import type { Metadata } from "next";
import { Nav } from "@/components/nav";
import { Footer } from "@/components/footer";
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
    a: "Pantheon is our orchestration suite: typed connectors into your backend, a planner that decomposes jobs into steps, a durable runtime that survives crashes and slow upstreams, and an append-only audit log covering every action.",
  },
  {
    q: "How do agents access our systems?",
    a: "Through typed connectors - Postgres, REST, gRPC, and message queues - using scoped, audited credentials. Credentials are minted per step with least privilege and revoked on completion.",
  },
  {
    q: "What happens when an agent is not confident?",
    a: "When confidence drops below your threshold, the agent stops and escalates to a human queue with the full decision trace attached, so a person can resolve it in seconds instead of re-deriving context.",
  },
  {
    q: "Is every action logged?",
    a: "Yes. Every action lands in an append-only audit log with the full prompt, tool call, and resulting diff. Any run can be replayed at any time.",
  },
  {
    q: "Where can Obsidura run?",
    a: "Three deployment options: our fully managed cloud, a private VPC inside your own AWS or GCP account, or air-gapped on-premises on your hardware.",
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
      <Nav />
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
      <Footer />
    </>
  );
}
