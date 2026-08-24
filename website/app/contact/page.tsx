import type { Metadata } from "next";
import { ContactForm } from "@/components/contact-form";
import { Engraving } from "@/components/ui/engraving";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderMark } from "@/components/ui/meander-mark";
import { SOCIALS } from "@/lib/socials";

export const metadata: Metadata = {
  title: "Contact - Obsidura",
  description:
    "Get in touch with Obsidura — book a demo, ask about deployment, or write directly to the officers of the company.",
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
    name: "Ethan Pascuales",
    role: "Chief Technology Officer",
    email: "ethan@obsidura.com",
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
            <p className="kicker mb-6 text-accent">v &mdash; send word</p>
            <h1 className="font-display text-[clamp(2.75rem,6vw,4.5rem)] leading-[1.02] font-light tracking-tight">
              Tell us what you are{" "}
              <span className="headline-emph">trying to run.</span>
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

      {/* The directory: Hermes carries the message; the officers receive it.
          Same two-column mount as the chapter pages - engraving beside
          text - so the page reads as one of the family. */}
      <section className="border-t border-rule">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-16 lg:grid-cols-[1fr_1.15fr] lg:gap-16 lg:py-24">
          <div className="hidden lg:block">
            <Engraving name="hermes" maxHeight={560} dim />
            <p className="kicker mt-4 text-center !text-[10px]">
              hermes, messenger of the gods
            </p>
          </div>

          <div>
            <p className="kicker mb-6 text-accent">the directory</p>
            <h2 className="font-display text-[clamp(2rem,4vw,3rem)] leading-[1.05] font-light tracking-tight">
              Or write to <span className="headline-emph">a person.</span>
            </h2>

            <ul className="mt-10">
              {OFFICERS.map(({ name, role, email }) => (
                <li
                  key={email}
                  className="flex flex-col gap-1.5 border-t border-rule py-5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6"
                >
                  <div>
                    <p className="font-display text-2xl font-light tracking-tight">
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

            <div className="mt-12 border-t border-rule pt-6">
              <p className="kicker mb-4 flex items-center gap-2.5">
                <MeanderMark size={10} />
                obsidura, elsewhere
              </p>
              <div className="flex flex-wrap gap-x-8 gap-y-3">
                {SOCIALS.map(({ label, href }) => (
                  <a
                    key={href}
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="kicker link-sweep transition-colors hover:text-ink"
                  >
                    {label} &rarr;
                  </a>
                ))}
              </div>
              <p className="mt-4 font-mono text-[12px] leading-relaxed text-ink-mute">
                We are @obsidura on every platform.
              </p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
