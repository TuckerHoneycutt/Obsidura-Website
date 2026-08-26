import Link from "next/link";
import { Engraving } from "@/components/ui/engraving";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderMark } from "@/components/ui/meander-mark";
import { Reveal } from "@/components/ui/reveal";
import type { EngravingName } from "@/lib/engravings";

export type SubpageSection = {
  heading: string;
  body?: string[];
  bullets?: string[];
};

export type RelatedLink = {
  label: string;
  href: string;
};

/**
 * Shared layout for the standalone landing pages (/integrations,
 * /deployment/*, ...). Each page supplies data; the composition - kicker,
 * two-part headline, mono lede, ruled sections, related links, and the
 * closing demo panel - stays identical across all of them.
 */
export function Subpage({
  kicker,
  headlineLead,
  headlineEmph,
  lede,
  art,
  artHeight = 560,
  sections,
  related,
}: {
  kicker: string;
  headlineLead: string;
  headlineEmph: string;
  lede: string;
  /** Engraving mounted beside the hero, as on the chapter pages. */
  art?: EngravingName;
  artHeight?: number;
  sections: SubpageSection[];
  related: RelatedLink[];
}) {
  const hero = (
    <Reveal>
      <p className="kicker mb-6 text-accent">{kicker}</p>
      <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
        {headlineLead} <span className="headline-emph">{headlineEmph}</span>
      </h1>
      <p className="lede-copy mt-6 max-w-xl">{lede}</p>
    </Reveal>
  );

  return (
    <main className="flex-1">
      <section className="relative">
        {/* With art, the hero widens to the chapter pages' two-column
            mount - text beside the engraving - and the reading column
            resumes below. Without it, nothing changes. */}
        {art ? (
          <div className="mx-auto max-w-6xl px-5 pt-16 lg:pt-24">
            <div className="grid items-center gap-10 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
              {hero}
              <Reveal delay={0.1}>
                <Engraving name={art} maxHeight={artHeight} dim />
              </Reveal>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl px-5 pt-16 lg:pt-24">{hero}</div>
        )}
        <div className="mx-auto max-w-3xl px-5 pb-20 lg:pb-28">
          <div className="mt-14 space-y-12">
            {sections.map(({ heading, body, bullets }, i) => (
              <Reveal key={heading} delay={Math.min(i * 0.06, 0.18)}>
                <h2 className="font-display text-[1.75rem] font-medium tracking-tight">
                  {heading}
                </h2>
                {body?.map((p) => (
                  <p key={p} className="body-copy mt-3">
                    {p}
                  </p>
                ))}
                {bullets && (
                  <ul className="mt-4 space-y-3">
                    {bullets.map((b) => (
                      <li key={b} className="body-copy flex gap-3">
                        <MeanderMark
                          size={10}
                          className="mt-2 text-ink-faint"
                        />
                        {b}
                      </li>
                    ))}
                  </ul>
                )}
              </Reveal>
            ))}
          </div>

          <Reveal className="mt-14 border-t border-rule pt-6">
            <p className="kicker mb-4">further reading</p>
            <div className="flex flex-wrap gap-x-8 gap-y-3">
              {related.map(({ label, href }) => (
                <Link
                  key={href}
                  href={href}
                  className="kicker link-sweep transition-colors hover:text-ink"
                >
                  {label} &rarr;
                </Link>
              ))}
            </div>
          </Reveal>

          <Reveal delay={0.08}>
            <FramePanel className="mt-14 bg-paper-warm/40">
              <div className="flex flex-col items-start gap-6 px-6 py-8 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="font-display text-3xl font-light tracking-tight">
                    Put Pantheon to work.
                  </h2>
                  <p className="body-copy mt-2 max-w-md text-ink-mute">
                    A 30-minute call. We map one job you already do by hand
                    and show you the audit log by the end of it.
                  </p>
                </div>
                <Link
                  href="/contact"
                  className="kicker inline-block shrink-0 bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
                >
                  Book a demo
                </Link>
              </div>
            </FramePanel>
          </Reveal>
        </div>
      </section>
    </main>
  );
}
