"use client";

import { useRef } from "react";
import { useInView } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * A single unit of the Greek key (meander) drawn as SVG strokes - the
 * square spiral used as the site's recurring Pantheon motif. SVG rather
 * than a unicode character so it renders identically on every platform.
 */
export function MeanderMark({
  size = 12,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 12 12"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="square"
      aria-hidden
      className={cn("inline-block shrink-0", className)}
    >
      <path d="M1 11V1h10v7H5V5h3" pathLength={1} />
    </svg>
  );
}

/**
 * A running Greek key band: the meander unit repeated edge to edge, the
 * way it appears on temple friezes and pottery rims. Wipes on left to
 * right when scrolled into view, like a band being carved. A fixed
 * pattern id is safe here because every instance renders the identical
 * tile.
 */
export function MeanderFrieze({ className }: { className?: string }) {
  const ref = useRef<SVGSVGElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10% 0px" });

  return (
    <svg
      ref={ref}
      aria-hidden
      className={cn(
        "frieze-wipe block w-full text-ink-faint",
        inView && "in-view",
        className
      )}
      height="12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.1"
      strokeLinecap="square"
    >
      <defs>
        <pattern
          id="meander-frieze"
          width="12"
          height="12"
          patternUnits="userSpaceOnUse"
        >
          <path d="M1.5 9.5V2.5h9v5H6V5h2.5" />
        </pattern>
      </defs>
      <rect width="100%" height="12" stroke="none" fill="url(#meander-frieze)" />
    </svg>
  );
}

/**
 * A meander seal that interrupts a section's top border, like a stamp on
 * the rule line. Traces its stroke on when the section scrolls into view.
 * Parent section must be `relative` with a top border.
 */
export function MeanderDivider({ className }: { className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px 0px" });

  return (
    <span
      ref={ref}
      aria-hidden
      className={cn(
        "meander-draw absolute -top-[7px] left-1/2 -translate-x-1/2 bg-paper px-3 text-ink-faint",
        inView && "in-view",
        className
      )}
    >
      <MeanderMark size={11} />
    </span>
  );
}
