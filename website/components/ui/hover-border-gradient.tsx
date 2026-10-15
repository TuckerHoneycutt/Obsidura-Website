"use client";

import { useEffect, useState, type ElementType, type ReactNode } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

type Direction = "TOP" | "LEFT" | "BOTTOM" | "RIGHT";

const DIRECTIONS: Direction[] = ["TOP", "LEFT", "BOTTOM", "RIGHT"];

// Every gradient shares one shape - four numbers, then the same two stops -
// so motion can interpolate the numbers while the var() colour rides along.
const MOVING: Record<Direction, string> = {
  TOP: "radial-gradient(20.7% 50% at 50% 0%, var(--ink) 0%, transparent 100%)",
  LEFT: "radial-gradient(16.6% 43.1% at 0% 50%, var(--ink) 0%, transparent 100%)",
  BOTTOM:
    "radial-gradient(20.7% 50% at 50% 100%, var(--ink) 0%, transparent 100%)",
  RIGHT:
    "radial-gradient(16.2% 41.2% at 100% 50%, var(--ink) 0%, transparent 100%)",
};

const HIGHLIGHT =
  "radial-gradient(75% 181.16% at 50% 50%, var(--ink) 0%, transparent 100%)";

/**
 * Aceternity UI "Hover Border Gradient": a point of light orbits the
 * button's hairline border, and on hover floods the whole edge.
 *
 * Adapted: square corners to match the site's frames, the light drawn in
 * --ink instead of white-and-blue, and the fill in --paper so the button
 * inverts cleanly with the theme.
 */
export function HoverBorderGradient({
  children,
  containerClassName,
  className,
  as: Tag = "button",
  duration = 1,
  clockwise = true,
  ...props
}: {
  children: ReactNode;
  as?: ElementType;
  containerClassName?: string;
  className?: string;
  duration?: number;
  clockwise?: boolean;
  [key: string]: unknown;
}) {
  const [hovered, setHovered] = useState(false);
  const [direction, setDirection] = useState<Direction>("TOP");

  useEffect(() => {
    if (hovered) return;
    const interval = setInterval(() => {
      setDirection((prev) => {
        const i = DIRECTIONS.indexOf(prev);
        const next = clockwise
          ? (i - 1 + DIRECTIONS.length) % DIRECTIONS.length
          : (i + 1) % DIRECTIONS.length;
        return DIRECTIONS[next];
      });
    }, duration * 1000);
    return () => clearInterval(interval);
  }, [hovered, duration, clockwise]);

  return (
    <Tag
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={() => setHovered(false)}
      className={cn(
        "relative flex h-min w-fit flex-col flex-nowrap content-center items-center justify-center overflow-visible border border-rule bg-ink/10 p-px decoration-clone transition duration-500",
        containerClassName
      )}
      {...props}
    >
      <div className={cn("relative z-10 w-auto bg-paper px-4 py-2", className)}>
        {children}
      </div>
      <motion.div
        aria-hidden
        className="absolute inset-0 z-0 flex-none overflow-hidden"
        style={{ filter: "blur(2px)" }}
        initial={{ background: MOVING[direction] }}
        animate={{
          background: hovered
            ? [MOVING[direction], HIGHLIGHT]
            : MOVING[direction],
        }}
        transition={{ ease: "linear", duration }}
      />
      <div aria-hidden className="absolute inset-[2px] z-[1] flex-none bg-paper" />
    </Tag>
  );
}
