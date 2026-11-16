"use client";

import { FilmPlate, FilmProvider, useFilm } from "@/components/home/film";
import { CHAPTERS, NUMERALS, POINTS, timecode } from "@/lib/home-content";
import { cn } from "@/lib/utils";

/**
 * Which film chapters show each point. An editorial call, not something
 * the film states:
 *   I.   one engine, run anywhere   -> What we are, Reproducible
 *   II.  agents, permissions, audit -> How it works, Agents, safely
 *   III. security and cost          -> Inside the data center
 */
const POINT_CHAPTERS = [[1, 4], [2, 3], [5]];

const pointText =
  "font-display text-[1.0625rem] leading-[1.45] sm:text-[clamp(1.25rem,1.8vw,1.6rem)]";

/**
 * The three points beside the team film. The film holds still while the
 * points scroll; each point names the chapters that show it, and those play
 * the film from there. While a chapter plays, its point comes up to full
 * ink.
 */
export function FilmPoints() {
  return (
    <FilmProvider>
      <FilmPointsBody />
    </FilmProvider>
  );
}

function FilmPointsBody() {
  const { chapter } = useFilm();

  return (
    <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] lg:gap-14">
      {/* On phones the film pins under the nav and the points scroll
          beneath it, below a hairline; from lg it sits in its own column. */}
      <div className="sticky top-[4rem] z-10 -mx-5 border-b border-rule bg-paper px-5 pt-3 pb-4 md:top-[4.8125rem] lg:order-2 lg:mx-0 lg:self-start lg:border-b-0 lg:px-0 lg:pt-8 lg:pb-0">
        <FilmPlate />
        <p className="kicker mt-3 flex justify-between gap-4" aria-live="polite">
          <span>Now playing · {CHAPTERS[chapter].title}</span>
          <span className="tabular-nums">{timecode(CHAPTERS[chapter].at)}</span>
        </p>
      </div>

      <ol className="flex flex-col gap-10 lg:order-1 lg:gap-16 lg:py-8">
        {POINTS.map((text, i) => {
          const playing = POINT_CHAPTERS[i].includes(chapter);
          return (
            <li
              key={text}
              className="grid grid-cols-[2rem_1fr] gap-x-3 sm:grid-cols-[3.5rem_1fr] sm:gap-x-4"
            >
              <span
                aria-hidden
                className={cn(
                  "text-right transition-colors duration-500",
                  pointText,
                  playing ? "text-ink-mute" : "text-ink-faint"
                )}
              >
                {NUMERALS[i]}.
              </span>
              <div>
                <p
                  className={cn(
                    "transition-colors duration-500",
                    pointText,
                    playing ? "text-ink" : "text-ink-mute"
                  )}
                >
                  {text}
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {POINT_CHAPTERS[i].map((c) => (
                    <ChapterLink key={c} index={c} />
                  ))}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** A chapter named under a point, which plays the film from there. */
function ChapterLink({ index }: { index: number }) {
  const { chapter, seek } = useFilm();
  const c = CHAPTERS[index];
  return (
    <button
      type="button"
      onClick={() => seek(c.at)}
      className={cn(
        "kicker inline-flex items-baseline gap-2 border px-2.5 py-1.5 transition-colors",
        chapter === index
          ? "border-ink-mute !text-ink"
          : "border-rule hover:border-ink-faint hover:!text-ink-soft"
      )}
    >
      <span aria-hidden>▸</span>
      {c.title}
      <span className="tabular-nums text-ink-faint">{timecode(c.at)}</span>
    </button>
  );
}
