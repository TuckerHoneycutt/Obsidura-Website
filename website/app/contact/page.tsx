import type { Metadata } from "next";
import { ContactForm } from "@/components/contact-form";
import { SocialGlyph } from "@/components/social-icons";
import { CardSpotlight } from "@/components/ui/card-spotlight";
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

export default function ContactPage() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      {/* One section, two columns: everything about reaching or following
          the company on the left, the form on the right. The two stacks are
          about the same height, so neither side trails off into dead space. */}
      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl gap-10 px-5 pt-12 pb-14 lg:grid-cols-[1fr_1.15fr] lg:gap-14 lg:pt-16 lg:pb-16">
          <div>
            <h1 className="font-display text-[clamp(2.4rem,5.2vw,3.9rem)] leading-[1.02] font-light tracking-tight">
              Speak <span className="headline-emph">to us.</span>
            </h1>

            <div className="mt-8 space-y-4">
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

            <div className="mt-9 border-t border-rule pt-6">
              <p className="kicker mb-2 font-semibold text-accent">
                obsidura, elsewhere
              </p>
              <p className="font-mono text-[12px] leading-relaxed text-ink-mute">
                Keep up to date as we continue to build and ship on all
                platforms.
              </p>
              {/* Each profile wears a frame-panel dress: glyph, platform,
                  handle. The glyphs render in currentColor so the brand
                  marks sit in the site's ink rather than their own colors. */}
              {/* A pool of light follows the pointer across each card. */}
              <div className="mt-4 grid grid-cols-2 gap-2.5">
                {SOCIALS.map(({ label, handle, href }) => (
                  <CardSpotlight
                    key={href}
                    radius={140}
                    className="p-0 transition-colors hover:border-accent-deep"
                  >
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group flex items-center gap-3 px-3.5 py-3"
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
                  </CardSpotlight>
                ))}
              </div>
            </div>
          </div>

          <ContactForm />
        </div>
      </section>
    </main>
  );
}
