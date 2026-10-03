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
    "Common questions about Obsidura: what small software is, what Pantheon does, what it can run, how access is controlled, and how to get started.",
  alternates: {
    canonical: "/faq",
  },
};

// Rendered on the page and serialized as FAQPage structured data below -
// one source of truth so the markup never drifts from the visible copy.
// Deliberately high-level: the engine's internals stay off the public
// site, so every answer describes what Pantheon does, never how.
const QUESTIONS = [
  {
    q: "What is Obsidura?",
    a: "Obsidura is a cloud for small software: the purpose-built tools companies and teams build for their own unique use cases. Pantheon, our infrastructure engine, gives agents everything they need to build, deploy, and run that software across your organization - securely, and with every run recorded.",
  },
  {
    q: "What is small software?",
    a: "Purpose-built tools that will only ever have one or a handful of users: a tracker for the numbers your team actually watches, a workflow tool shaped to how you actually work, a prototype you want colleagues to try today. Agents have made this kind of software easy to build. Deploying, securing, and sharing it is the part that has stayed hard - and the part we solve.",
  },
  {
    q: "What is Pantheon?",
    a: "Pantheon is the engine underneath Obsidura. It runs your tools in a secure, governed environment: access is scoped to each person's role, work can pause for a human decision where you say it must, and everything that happens is recorded. We keep its internals off the marketing site on purpose - book a demo if you want the deep dive.",
  },
  {
    q: "What kinds of work can it run?",
    a: "Anything software and data can touch. A month-end performance pack, a nightly reconciliation, a bespoke tracker, a team workflow carried end to end, or a question asked in plain English and answered from your data - on a schedule, at the press of a button, or when another system calls in.",
  },
  {
    q: "How is access controlled?",
    a: "Access follows the person. What a tool or agent may reach is scoped to the role of whoever it is working for, checked every time rather than once at the start, and recorded. Two people can use the same tool and each only ever touches what they are allowed to touch.",
  },
  {
    q: "Is every action logged?",
    a: "Yes. Every run is recorded end to end - what ran, for whom, what it touched, and what it produced - so there is always an answer to what happened.",
  },
  {
    q: "Where can it run?",
    a: "In our managed cloud, in a private VPC inside your own cloud account, or on-premises. The security model is the same in all three.",
  },
  {
    q: "How do we get started?",
    a: "Book a demo through the contact page. We map one of your use cases on a 30-minute call and show you what it looks like running by the end of it.",
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
      <main id="content" tabIndex={-1} className="flex-1">
        <section className="relative">
          <div className="relative mx-auto max-w-3xl px-5 pt-16 pb-20 lg:pt-24 lg:pb-28">
            {/* On wide screens the appendix label hangs in the left margin
                as true marginalia - the gutter annotating the text, the way
                a printed appendix would - so the column's offset reads as
                set on purpose rather than left over. */}
            <p className="kicker mb-6 text-accent xl:absolute xl:top-[6.6rem] xl:right-full xl:mr-14 xl:mb-0 xl:w-36 xl:text-right">
              appendix i &mdash; questions
            </p>
            <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
              Frequently asked{" "}
              <span className="headline-emph">questions.</span>
            </h1>
            <p className="lede-copy mt-6 max-w-xl">
              What Obsidura is, what Pantheon runs, and how access is
              controlled. Something missing? Send word through the contact
              page.
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
