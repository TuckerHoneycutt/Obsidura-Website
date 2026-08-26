import type { Metadata } from "next";
import { ContactForm } from "@/components/contact-form";
import { SocialGlyph } from "@/components/social-icons";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderMark } from "@/components/ui/meander-mark";
import { SOCIALS } from "@/lib/socials";

export const metadata: Metadata = {
  title: "Contact - Obsidura",
  description:
    "Get in touch with Obsidura — book a demo, ask about deployment, or send word to the company. We are @obsidura on every platform.",
  alternates: {
    canonical: "/contact",
  },
};

const OFFICERS = [
  {
    name: "Jarrett Whaley",
    role: "Chief Executive Officer",
    email: "jarrett@obsidura.com",
  },
  {
    name: "Tucker Honeycutt",
    role: "Chief Operating Officer",
    email: "tucker@obsidura.com",
  },
];

export default function ContactPage() {
  return (
    <main className="flex-1">
      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 pt-16 pb-20 lg:grid-cols-[1fr_1.15fr] lg:gap-16 lg:pt-24 lg:pb-28">
          <div>
            <p className="kicker mb-6 text-accent">
              obsidura &mdash; intelligent infrastructure
            </p>
            <h1 className="font-display text-[clamp(2.75rem,6vw,4.5rem)] leading-[1.02] font-light tracking-tight">
              Speak <span className="headline-emph">to us.</span>
            </h1>
            <p className="lede-copy mt-7 max-w-md">
              Design partners, deployment questions, or a thirty-minute demo
              — send word and we will see it carried to the right person.
            </p>

            <div className="mt-10 space-y-4">
              <FramePanel className="inline-block bg-paper-warm/40 px-4 py-3">
                <p className="kicker flex items-center gap-2.5">
                  <MeanderMark size={10} />
                  <a
                    href="mailto:contact@obsidura.com"
                    className="link-sweep transition-colors hover:text-ink"
                  >
                    contact@obsidura.com
                  </a>
                </p>
              </FramePanel>
              <p className="font-mono text-[12px] leading-relaxed text-ink-mute">
                Prefer email directly? That address lands in the same inbox.
              </p>
            </div>
          </div>

          <ContactForm />
        </div>
      </section>

      <section className="border-t border-rule">
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-24">
          <div className="max-w-2xl">
            <p className="kicker mb-6 text-accent">obsidura, elsewhere</p>
            <h2 className="font-display text-[clamp(2rem,4vw,3rem)] leading-[1.05] font-light tracking-tight">
              Keep up with <span className="headline-emph">the works.</span>
            </h2>
            <p className="lede-copy mt-6 max-w-xl">
              Keep up to date as we continue to build and ship on all
              platforms.
            </p>

            {/* Each profile wears a frame-panel dress: glyph, platform,
                handle. The glyphs render in currentColor so the brand
                marks sit in the site's ink rather than their own colors. */}
            <div className="mt-9 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              {SOCIALS.map(({ label, handle, href }) => (
                <a
                  key={href}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-center gap-3 border border-rule bg-paper-warm/40 px-3.5 py-3 transition-colors hover:border-accent-deep"
                >
                  <SocialGlyph
                    label={label}
                    className="text-ink-mute transition-colors group-hover:text-ink"
                  />
                  <span className="min-w-0">
                    <span className="kicker block !text-[10px] transition-colors group-hover:text-ink">
                      {label}
                    </span>
                    <span className="block truncate font-mono text-[11px] text-ink-faint">
                      {handle}
                    </span>
                  </span>
                </a>
              ))}
            </div>

            {/* The officers wait behind the fold - closed until asked for,
                so the channels stay the headline act. */}
            <Accordion
              type="single"
              collapsible
              className="mt-10 border-t border-rule"
            >
              <AccordionItem value="officers">
                <AccordionTrigger className="py-5">
                  <span className="font-display text-2xl font-light tracking-tight">
                    The Team
                  </span>
                </AccordionTrigger>
                <AccordionContent className="!pb-5">
                  <ul>
                    {OFFICERS.map(({ name, role, email }) => (
                      <li
                        key={email}
                        className="flex flex-col gap-1 border-t border-rule py-4 first:border-t-0 first:pt-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6"
                      >
                        <div>
                          <p className="font-display text-xl font-light tracking-tight">
                            {name}
                          </p>
                          <p className="kicker mt-1 !text-[10px] text-ink-mute">
                            {role}
                          </p>
                        </div>
                        <a
                          href={`mailto:${email}`}
                          className="kicker link-sweep shrink-0 transition-colors hover:text-ink"
                        >
                          {email}
                        </a>
                      </li>
                    ))}
                  </ul>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        </div>
      </section>
    </main>
  );
}
