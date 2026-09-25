"use client";

import { useRef } from "react";
import { useInView } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * A step numeral that lights when the TracingRail's fill reaches it. The
 * rail fills to a line 70% down the viewport, so the numeral watches that
 * same line: the root is trimmed 30% from the bottom, and the numeral counts
 * as passed once it is above it. Scrolling back up dims it again, matching
 * the rail as it recedes.
 *
 * Below lg there is no rail, and under reduced motion no fill is drawn, so
 * in both cases the numeral simply holds full accent. The colors are
 * forced because .kicker sets its own color outside Tailwind's layers.
 */
export function RailNumeral({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLParagraphElement>(null);
  const passed = useInView(ref, { margin: "0px 0px -30% 0px" });

  return (
    <p
      ref={ref}
      className={cn(
        "kicker !text-accent transition-colors duration-300",
        !passed && "lg:motion-safe:!text-ink-faint",
        className
      )}
    >
      {children}
    </p>
  );
}
