"use client";

import { useFilm } from "@/components/sketches/film";
import { CHAPTERS, FILM_LENGTH, timecode } from "@/lib/home-content";
import { cn } from "@/lib/utils";

/**
 * The film's contents page: every chapter by its own label and start, the
 * playing one in full ink with its rule filling as it plays. Clicking a
 * row plays the film from there.
 */
export function ChapterIndex({ className }: { className?: string }) {
  const { time, chapter, seek } = useFilm();

  return (
    <nav aria-label="Film chapters" className={className}>
      <p className="kicker mb-4">Contents</p>
      <ol className="grid grid-cols-2 gap-x-6 lg:grid-cols-1">
        {CHAPTERS.map((c, i) => {
          const end = CHAPTERS[i + 1]?.at ?? FILM_LENGTH;
          const fill =
            i === chapter ? ((time - c.at) / (end - c.at)) * 100 : i < chapter ? 100 : 0;
          return (
            <li key={c.at}>
              <button
                type="button"
                onClick={() => seek(c.at)}
                aria-current={i === chapter ? "true" : undefined}
                className={cn(
                  "group grid w-full grid-cols-[2.75rem_1fr] items-baseline gap-x-2 py-2.5 text-left transition-colors",
                  i === chapter ? "text-ink" : "text-ink-mute hover:text-ink-soft"
                )}
              >
                <span className="kicker !text-inherit tabular-nums">{timecode(c.at)}</span>
                <span className="font-display text-[1.0625rem] leading-snug sm:text-lg">
                  {c.title}
                </span>
              </button>
              <span aria-hidden className="relative block h-px bg-rule">
                <span
                  className={cn(
                    "absolute inset-y-0 left-0 transition-[width] duration-300 ease-linear",
                    i === chapter ? "bg-ink" : "bg-ink-faint"
                  )}
                  style={{ width: `${Math.min(Math.max(fill, 0), 100)}%` }}
                />
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** A chapter named in running text, which plays the film from there. */
export function ChapterLink({ index }: { index: number }) {
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

