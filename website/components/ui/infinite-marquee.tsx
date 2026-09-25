import { Fragment, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/** A plain string, or an entry with a mark set in front of its name and an
    optional status note set after it (e.g. "planned"). */
export type MarqueeItem =
  | string
  | { label: string; icon?: ReactNode; note?: string };

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
  items: MarqueeItem[];
  className?: string;
}) {
  const track = [...items, ...items];
  return (
    <div className={cn("overflow-hidden mask-fade-x", className)}>
      {/* Duration grows with the list so a longer strip keeps the same
          reading pace instead of racing to finish the loop in 36s. */}
      <div
        className="animate-marquee flex w-max items-center gap-10"
        style={{ animationDuration: `${Math.max(36, items.length * 7)}s` }}
      >
        {track.map((raw, i) => {
          const item: Exclude<MarqueeItem, string> =
            typeof raw === "string" ? { label: raw } : raw;
          return (
            <Fragment key={`${item.label}-${i}`}>
              {/* The second copy exists only for the seamless loop; hiding
                  it from assistive tech keeps the list from being read
                  twice. */}
              <span
                aria-hidden={i >= items.length || undefined}
                className={cn(
                  "kicker flex items-center gap-2.5 whitespace-nowrap",
                  item.note ? "text-ink-mute" : "text-ink-soft"
                )}
              >
                {item.icon && (
                  <span className="flex size-[1.4em] shrink-0 [&>svg]:size-full">
                    {item.icon}
                  </span>
                )}
                {item.label}
                {item.note && (
                  <span className="border border-ink-faint px-1.5 py-0.5 !text-[0.85em]">
                    {item.note}
                  </span>
                )}
              </span>
              <span
                aria-hidden
                className="size-[3px] shrink-0 rotate-45 bg-ink-faint"
              />
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
