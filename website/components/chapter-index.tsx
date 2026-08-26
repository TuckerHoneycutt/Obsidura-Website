import Link from "next/link";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { CHAPTERS } from "@/lib/chapters";

/**
 * The way in. A numbered table of contents rather than a row of cards -
 * the site reads as five chapters now, and the index should say so plainly.
 * Every entry is tagged nav-forward, so the page slides in the direction the
 * reader is traveling.
 */
export function ChapterIndex() {
  return (
    <section className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-14 lg:py-20">
        <Reveal>
          <p className="kicker text-accent">the system, in five parts</p>
        </Reveal>

        <ol className="mt-8 border-t border-rule">
          {CHAPTERS.map((chapter, i) => (
            <Reveal key={chapter.slug} delay={Math.min(i * 0.06, 0.24)}>
              <li>
                <Link
                  href={`/${chapter.slug}`}
                  transitionTypes={["nav-forward"]}
                  className="group flex flex-col gap-2 border-b border-rule py-6 transition-colors hover:bg-paper-warm/50 sm:flex-row sm:items-baseline sm:gap-8 sm:px-3"
                >
                  <span className="kicker w-10 shrink-0 text-accent">
                    {chapter.numeral}
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="font-display block text-[clamp(1.4rem,2.7vw,2.1rem)] leading-tight font-light tracking-tight">
                      {chapter.label}
                    </span>
                    <span className="body-copy mt-1.5 block text-ink-mute">
                      {chapter.blurb}
                    </span>
                  </span>

                  <span
                    aria-hidden
                    className="kicker shrink-0 transition-transform group-hover:translate-x-1"
                  >
                    &rarr;
                  </span>
                </Link>
              </li>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}
