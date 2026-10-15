import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

const SPEEDS = { fast: "20s", normal: "40s", slow: "80s" } as const;

/**
 * Aceternity UI "Infinite Moving Cards": a band of cards that drifts
 * sideways forever and pauses under the pointer.
 *
 * Adapted: the stock version clones its own DOM nodes after mount, which
 * React does not know about and which screen readers announce twice. Here
 * the second run is rendered by React and marked aria-hidden, so it needs
 * no client JavaScript at all. Cards are square hairline plates on
 * --paper-warm instead of rounded zinc gradients.
 */
export function InfiniteMovingCards({
  items,
  direction = "left",
  speed = "slow",
  pauseOnHover = true,
  className,
}: {
  items: { quote: string; title: string }[];
  direction?: "left" | "right";
  speed?: keyof typeof SPEEDS;
  pauseOnHover?: boolean;
  className?: string;
}) {
  const card = (item: (typeof items)[number], key: string, hidden: boolean) => (
    <li
      key={key}
      aria-hidden={hidden || undefined}
      className="relative w-[300px] max-w-full shrink-0 border border-rule bg-paper-warm/60 px-7 py-6 md:w-[380px]"
    >
      <blockquote>
        <p className="kicker !text-[10px]">{item.title}</p>
        <p className="mt-4 font-display text-[1.35rem] leading-snug font-light tracking-tight text-ink">
          {item.quote}
        </p>
      </blockquote>
    </li>
  );

  return (
    <div
      className={cn(
        "relative z-20 overflow-hidden [mask-image:linear-gradient(to_right,transparent,white_15%,white_85%,transparent)]",
        className
      )}
      style={
        {
          "--animation-duration": SPEEDS[speed],
          "--animation-direction": direction === "left" ? "forwards" : "reverse",
        } as CSSProperties
      }
    >
      <ul
        className={cn(
          "animate-scroll flex w-max min-w-full shrink-0 flex-nowrap gap-4 py-4",
          pauseOnHover && "hover:[animation-play-state:paused]"
        )}
      >
        {items.map((item, i) => card(item, `a-${i}`, false))}
        {items.map((item, i) => card(item, `b-${i}`, true))}
      </ul>
    </div>
  );
}
