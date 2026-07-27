import { cn } from "@/lib/utils";

/**
 * Aceternity-style infinite moving items strip. Items are duplicated once and
 * translated by exactly half the track width for a seamless loop.
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
          <span
            key={`${item}-${i}`}
            className="kicker whitespace-nowrap text-ink-faint"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
