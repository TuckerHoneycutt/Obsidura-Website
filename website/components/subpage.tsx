import Link from "next/link";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderMark } from "@/components/ui/meander-mark";
import { Reveal } from "@/components/ui/reveal";

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
 * Shared layout for the standalone landing pages (/platform, /solutions/*,
 * /deployment/*, ...). Each page supplies data; the composition - kicker,
 * two-part headline, mono lede, ruled sections, related links, and the
 * closing demo panel - stays identical across all of them.
 */
export function Subpage({
  kicker,
  headlineLead,
  headlineEmph,
  lede,
  sections,
  related,
}: {
  kicker: string;
  headlineLead: string;
  headlineEmph: string;
  lede: string;
  sections: SubpageSection[];
  related: RelatedLink[];
}) {
  return (
    <main className="flex-1">
      <section className="relative">
        <div className="mx-auto max-w-3xl px-5 pt-16 pb-20 lg:pt-24 lg:pb-28">
          <Reveal>
            <p className="kicker mb-6 text-accent">{kicker}</p>
            <h1 className="font-display text-[clamp(2.5rem,5.5vw,4rem)] leading-[1.04] font-light tracking-tight">
              {headlineLead}{" "}
              <span className="headline-emph">{headlineEmph}</span>
            </h1>
            <p className="mt-6 max-w-xl font-mono text-sm leading-relaxed text-ink-soft">
              {lede}
            </p>
          </Reveal>

          <div className="mt-14 space-y-12">
            {sections.map(({ heading, body, bullets }, i) => (
              <Reveal key={heading} delay={Math.min(i * 0.06, 0.18)}>
                <h2 className="font-display text-2xl font-medium tracking-tight">
                  {heading}
                </h2>
                {body?.map((p) => (
                  <p
                    key={p}
                    className="mt-3 font-mono text-sm leading-relaxed text-ink-soft"
                  >
                    {p}
                  </p>
                ))}
                {bullets && (
                  <ul className="mt-4 space-y-3">
                    {bullets.map((b) => (
                      <li
                        key={b}
                        className="flex gap-3 font-mono text-sm leading-relaxed text-ink-soft"
                      >
                        <MeanderMark
                          size={10}
                          className="mt-1 text-ink-faint"
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
                    Put agents on your backend.
                  </h2>
                  <p className="mt-2 max-w-md font-mono text-sm text-ink-mute">
                    A 30-minute call. We map one workflow and show you the
                    audit log by the end of it.
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
