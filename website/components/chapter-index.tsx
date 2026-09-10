import Link from "next/link";
import { ChapterIndexArt } from "@/components/chapter-index-art";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { CHAPTERS } from "@/lib/chapters";

/**
 * The way in. A numbered table of contents rather than a row of cards -
 * the site reads as five chapters now, and the index should say so plainly.
 * Every entry is tagged nav-forward, so the page slides in the direction the
 * reader is traveling.
 *
 * The numerals are set in the display serif at chapter scale - the sequence
 * is real structure, so it gets the carved treatment rather than a label -
 * and a hovered row surfaces a ghost band of its chapter's engraving in the
 * otherwise empty right side. The hovered numeral takes gilt: the one drop
 * of the sacred color the homepage spends.
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
                  className="group relative flex flex-col gap-2 overflow-hidden border-b border-rule py-6 transition-colors hover:bg-paper-warm/50 sm:flex-row sm:items-baseline sm:gap-8 sm:px-3"
                >
                  {/* Deploy's plates belong to its dominion cards, so the
                      index previews Hermes instead - the one who travels
                      between all three realms. */}
                  <ChapterIndexArt name={chapter.art ?? "hermes"} />

                  <span className="font-display relative w-12 shrink-0 text-[clamp(1.8rem,2.6vw,2.35rem)] leading-none font-light uppercase text-accent transition-colors group-hover:[color:var(--gilt)] group-focus-visible:[color:var(--gilt)] sm:w-16">
                    {chapter.numeral}
                  </span>

                  <span className="relative min-w-0 flex-1">
                    <span className="font-display block text-[clamp(1.4rem,2.7vw,2.1rem)] leading-tight font-light tracking-tight">
                      {chapter.label}
                    </span>
                    <span className="body-copy mt-1.5 block text-ink-mute">
                      {chapter.blurb}
                    </span>
                  </span>

                  <span aria-hidden className="kicker relative shrink-0">
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
