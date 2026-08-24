import type { Metadata } from "next";
import Link from "next/link";
import { SocialGlyph } from "@/components/social-icons";
import { Engraving } from "@/components/ui/engraving";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderMark } from "@/components/ui/meander-mark";
import { SOCIALS } from "@/lib/socials";

export const metadata: Metadata = {
  title: "About - Obsidura",
  description:
    "We post what we ship. Obsidura is @obsidura on every platform, and the officers are an email away.",
  alternates: {
    canonical: "/about",
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

export default function AboutPage() {
  return (
    <main className="flex-1">
      <section className="relative overflow-hidden">
        <div className="mx-auto max-w-6xl px-5 pt-16 pb-20 lg:pt-24 lg:pb-28">
          <p className="kicker mb-6 text-accent">about us</p>
          <h1 className="font-display max-w-3xl text-[clamp(2.75rem,6vw,4.5rem)] leading-[1.02] font-light tracking-tight">
            Keep up with <span className="headline-emph">the works.</span>
          </h1>
          <p className="lede-copy mt-7 max-w-xl">
            Keep up to date as we continue to build and ship on all platforms.
          </p>
        </div>
      </section>

      {/* The channels: Hermes carries the dispatches. Same two-column mount
          as the chapter pages - engraving beside text - so the page reads
          as one of the family. */}
      <section className="border-t border-rule">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-16 lg:grid-cols-[1fr_1.15fr] lg:gap-16 lg:py-24">
          <div className="hidden lg:block">
            <Engraving name="hermes" maxHeight={560} dim />
            <p className="kicker mt-4 text-center !text-[10px]">
              hermes, messenger of the gods
            </p>
          </div>

          <div>
            <p className="kicker mb-6 text-accent">obsidura, elsewhere</p>
            <h2 className="font-display text-[clamp(2rem,4vw,3rem)] leading-[1.05] font-light tracking-tight">
              Follow <span className="headline-emph">along.</span>
            </h2>

            {/* Each profile wears a frame-panel dress: glyph, platform,
                handle. The glyphs render in currentColor so the brand
                marks sit in the site's ink rather than their own colors. */}
            <div className="mt-10 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
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

            {/* A short directory under the channels - the socials stay the
                headline act; the officers ride below for whoever needs a
                person. */}
            <div className="mt-12 border-t border-rule pt-6">
              <p className="kicker mb-2 flex items-center gap-2.5">
                <MeanderMark size={10} />
                or write to a person
              </p>
              <ul>
                {OFFICERS.map(({ name, role, email }) => (
                  <li
                    key={email}
                    className="flex flex-col gap-1 border-b border-rule py-4 last:border-b-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6"
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
            </div>

            <div className="mt-8 space-y-4 border-t border-rule pt-6">
              <FramePanel className="inline-block bg-paper-warm/40 px-4 py-3">
                <p className="kicker flex items-center gap-2.5">
                  <MeanderMark size={10} />
                  <Link
                    href="/contact"
                    className="link-sweep transition-colors hover:text-ink"
                  >
                    send word &rarr;
                  </Link>
                </p>
              </FramePanel>
              <p className="font-mono text-[12px] leading-relaxed text-ink-mute">
                Have something to run? The contact page carries it to the
                right person.
              </p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
