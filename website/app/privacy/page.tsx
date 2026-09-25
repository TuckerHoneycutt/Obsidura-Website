import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy - Obsidura",
  description:
    "How Obsidura collects, uses, and protects information submitted through this website.",
  alternates: {
    canonical: "/privacy",
  },
};

const SECTIONS: { heading: string; body: string[] }[] = [
  {
    heading: "What we collect",
    body: [
      "When you contact us through this site, we collect the information you choose to provide: your name, email address, company, and message.",
      "Like most websites, our hosting and content-delivery providers process standard technical request data - such as IP address, browser type, and pages requested - to serve the site and protect it from abuse.",
      "We do not run third-party advertising trackers on this site.",
    ],
  },
  {
    heading: "How we use it",
    body: [
      "Contact information is used to respond to your inquiry, schedule demos, and follow up on conversations you start with us. That is the purpose you gave it to us for, and that is what it is used for.",
      "We do not sell your personal information.",
    ],
  },
  {
    heading: "Who we share it with",
    body: [
      "We use a small number of service providers to operate this site and our business - hosting, content delivery, and email. They process data on our behalf and are not permitted to use it for their own purposes.",
      "We may disclose information if required to do so by law.",
    ],
  },
  {
    heading: "Retention",
    body: [
      "We keep contact inquiries for as long as needed to handle the conversation and maintain our business records, and we delete them when they are no longer needed.",
    ],
  },
  {
    heading: "Your choices",
    body: [
      "You can ask us to access, correct, or delete the personal information we hold about you at any time by emailing contact@obsidura.com. We will respond to every reasonable request.",
    ],
  },
  {
    heading: "Changes",
    body: [
      "If this policy changes, we will update this page and revise the effective date below. Material changes will be noted plainly rather than buried.",
    ],
  },
];

// Title and section headings on the left, text on the right at lg.
const ROW =
  "grid gap-y-3 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-x-[clamp(3rem,6vw,6rem)]";

export default function PrivacyPage() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <section className="relative">
        {/* Wide frame, reading-measure prose: the title and each section
            heading hold the left column, the policy text runs on the right. */}
        <div className="mx-auto max-w-shell px-gutter pt-16 pb-20 lg:pt-24 lg:pb-28">
          <div className="grid gap-y-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-x-[clamp(3rem,6vw,6rem)]">
            <div>
              <p className="kicker mb-6 text-accent">
                appendix ii &mdash; privacy
              </p>
              <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
                Privacy <span className="headline-emph">policy.</span>
              </h1>
            </div>
            <p className="lede-copy max-w-xl lg:self-end">
              The short version: we collect what you send us through the
              contact form, we use it to reply to you, and we do not sell
              it. The longer version follows.
            </p>
          </div>

          <div className="mt-14 space-y-10 lg:mt-20 lg:space-y-14">
            {SECTIONS.map(({ heading, body }) => (
              <div key={heading} className={ROW}>
                <h2 className="font-display text-2xl font-medium tracking-tight">
                  {heading}
                </h2>
                <div className="max-w-2xl space-y-3">
                  {body.map((p) => (
                    <p key={p} className="body-copy">
                      {p}
                    </p>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <p className="kicker mt-14 border-t border-rule pt-6 !text-[0.71875rem]">
            effective august 2026 &mdash; questions: contact@obsidura.com
          </p>
        </div>
      </section>
    </main>
  );
}
