import { Fragment } from "react";
import { cn } from "@/lib/utils";

/**
 * Aceternity-style infinite moving items strip. Items are duplicated once and
 * translated by exactly half the track width for a seamless loop. Words are
 * separated by small diamond interpuncts, the way ancient inscriptions
 * divided them.
 */
export function InfiniteMarquee({
  items,
  className,
}: {
  items: string[];
  className?: string;
}) {
  const track = [...items, ...items];
  return (
    <div className={cn("overflow-hidden mask-fade-x", className)}>
      <div className="animate-marquee flex w-max items-center gap-10">
        {track.map((item, i) => (
          <Fragment key={`${item}-${i}`}>
            <span className="kicker whitespace-nowrap text-ink-faint">
              {item}
            </span>
            <span
              aria-hidden
              className="size-[3px] shrink-0 rotate-45 bg-ink-faint"
            />
          </Fragment>
        ))}
      </div>
    </div>
  );
}
