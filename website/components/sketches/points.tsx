import type { ReactNode } from "react";
import { NUMERALS, POINTS } from "@/lib/home-content";

const pointText =
  "font-display text-[1.0625rem] leading-[1.45] sm:text-[clamp(1.25rem,1.8vw,1.6rem)]";

/** The three points as the hero sets them, with room for something under each. */
export function Points({ after }: { after?: (i: number) => ReactNode }) {
  return (
    <ol className="flex max-w-2xl flex-col gap-8 sm:gap-10">
      {POINTS.map((text, i) => (
        <li
          key={text}
          className="grid grid-cols-[2rem_1fr] gap-x-3 sm:grid-cols-[3.5rem_1fr] sm:gap-x-4"
        >
          <span aria-hidden className={`text-right text-ink-faint ${pointText}`}>
            {NUMERALS[i]}.
          </span>
          <div>
            <p className={`text-ink-soft ${pointText}`}>{text}</p>
            {after?.(i)}
          </div>
        </li>
      ))}
    </ol>
  );
}
