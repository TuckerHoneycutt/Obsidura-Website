import Link from "next/link";
import { Engraving } from "@/components/ui/engraving";
import { MeanderMark } from "@/components/ui/meander-mark";
import { Reveal } from "@/components/ui/reveal";
import { chapterAt, type Chapter as ChapterMeta } from "@/lib/chapters";

/** Directions are declared per link, not inferred - see the transitions CSS. */
const FORWARD = ["nav-forward"];
const BACK = ["nav-back"];

function Pager({ prev, next }: { prev?: ChapterMeta; next?: ChapterMeta }) {
  return (
    <nav
      aria-label="Chapters"
      className="relative border-t border-rule bg-paper-warm/30"
    >
      <div className="mx-auto grid max-w-6xl gap-px px-5 sm:grid-cols-2">
        {prev ? (
          <Link
            href={`/${prev.slug}`}
            transitionTypes={BACK}
            className="group flex flex-col justify-center border-b border-rule py-10 sm:border-b-0 sm:pr-8"
          >
            <span className="kicker !text-[10px]">
              &larr; {prev.numeral} &mdash; {prev.name}
            </span>
            <span className="font-display mt-2 text-2xl font-light tracking-tight transition-colors group-hover:text-ink-mute">
              {prev.headlineLead} {prev.headlineEmph}
            </span>
          </Link>
        ) : (
          <Link
            href="/"
            transitionTypes={BACK}
            className="group flex flex-col justify-center border-b border-rule py-10 sm:border-b-0 sm:pr-8"
          >
            <span className="kicker !text-[10px]">&larr; the index</span>
            <span className="font-display mt-2 text-2xl font-light tracking-tight transition-colors group-hover:text-ink-mute">
              Back to the beginning
            </span>
          </Link>
        )}

        {next ? (
          <Link
            href={`/${next.slug}`}
            transitionTypes={FORWARD}
            className="group flex flex-col justify-center py-10 sm:items-end sm:border-l sm:border-rule sm:pl-8 sm:text-right"
          >
            <span className="kicker !text-[10px] text-accent">
              {next.numeral} &mdash; {next.name} &rarr;
            </span>
            <span className="font-display mt-2 text-2xl font-light tracking-tight transition-colors group-hover:text-ink-mute">
              {next.headlineLead} {next.headlineEmph}
            </span>
          </Link>
        ) : (
          <Link
            href="/contact"
            transitionTypes={FORWARD}
            className="group flex flex-col justify-center py-10 sm:items-end sm:border-l sm:border-rule sm:pl-8 sm:text-right"
          >
            <span className="kicker !text-[10px] text-accent">
              the last word &rarr;
            </span>
            <span className="font-display mt-2 text-2xl font-light tracking-tight transition-colors group-hover:text-ink-mute">
              Put agents on your backend
            </span>
          </Link>
        )}
      </div>
    </nav>
  );
}

/**
 * The frame every chapter page shares: the numbered opening, the engraving at
 * full size, the chapter's own content, and a pager into the chapters either
 * side of it. The engraving is the whole point of giving each chapter a page
 * of its own - at 157 columns it needs the room.
 */
export function Chapter({
  slug,
  children,
}: {
  slug: string;
  children: React.ReactNode;
}) {
  const { chapter, prev, next } = chapterAt(slug);

  return (
    <main className="flex-1">
      <section className="relative overflow-hidden">
        <div className="mx-auto max-w-6xl px-5 pt-16 pb-12 lg:pt-24">
          <Reveal className="max-w-3xl">
            <p className="kicker flex items-center gap-2.5 text-accent">
              <MeanderMark size={10} />
              {chapter.numeral} &mdash; {chapter.name}
            </p>
            <h1 className="font-display mt-6 text-[clamp(2.5rem,5.5vw,4rem)] leading-[1.04] font-light tracking-tight">
              {chapter.headlineLead}{" "}
              <span className="headline-emph">{chapter.headlineEmph}</span>
            </h1>
            <p className="lede-copy mt-6 max-w-2xl">{chapter.lede}</p>
          </Reveal>
        </div>

        {chapter.art && (
          <div className="mx-auto max-w-6xl px-5 pb-16">
            <Engraving
              name={chapter.art}
              maxHeight={chapter.artHeight}
              dim
            />
          </div>
        )}
      </section>

      {children}

      <Pager prev={prev} next={next} />
    </main>
  );
}
