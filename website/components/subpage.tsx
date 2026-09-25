import Link from "next/link";
import { DemoPanel } from "@/components/demo-panel";
import { Engraving } from "@/components/ui/engraving";
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
  leadLink,
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
  /** A sibling page covering the same ground from another side, offered
      right under the lede so the reader does not have to find it. */
  leadLink?: RelatedLink;
}) {
  const hero = (
    <Reveal>
      <p className="kicker mb-6 text-accent">{kicker}</p>
      <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
        {headlineLead} <span className="headline-emph">{headlineEmph}</span>
      </h1>
      <p className="lede-copy mt-6 max-w-xl">{lede}</p>
      {leadLink && (
        <Link
          href={leadLink.href}
          className="kicker link-sweep mt-6 inline-block text-accent transition-colors hover:text-ink"
        >
          {leadLink.label} &rarr;
        </Link>
      )}
    </Reveal>
  );

  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <section className="relative">
        <div className="mx-auto max-w-shell px-gutter pt-16 pb-20 lg:pt-24 lg:pb-28">
          {/* With art, the hero takes the chapter pages' two-column mount -
              text beside the engraving, the art given the wider span.
              Without it, the hero keeps its reading measure. */}
          {art ? (
            <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-[clamp(3rem,5vw,6rem)]">
              {hero}
              <Reveal delay={0.1}>
                <Engraving name={art} maxHeight={artHeight} dim />
              </Reveal>
            </div>
          ) : (
            <div className="max-w-3xl">{hero}</div>
          )}

          {/* From lg the sections run as ruled rows: the heading holds a
              left column, the prose keeps its measure in the right. */}
          <div className="mt-14 space-y-12 lg:mt-20 lg:space-y-0">
            {sections.map(({ heading, body, bullets }, i) => (
              <Reveal
                key={heading}
                delay={Math.min(i * 0.06, 0.18)}
                className="lg:grid lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] lg:gap-x-[clamp(3rem,5vw,6rem)] lg:border-t lg:border-rule lg:py-10"
              >
                <h2 className="font-display text-[1.75rem] leading-tight font-medium tracking-tight">
                  {heading}
                </h2>
                <div className="max-w-3xl lg:[&>:first-child]:mt-0">
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
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal className="mt-14 border-t border-rule pt-6 lg:mt-0 lg:grid lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] lg:gap-x-[clamp(3rem,5vw,6rem)] lg:py-10">
            <p className="kicker mb-4 lg:mb-0">further reading</p>
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
            <DemoPanel className="mt-14 lg:mt-6" />
          </Reveal>
        </div>
      </section>
    </main>
  );
}
