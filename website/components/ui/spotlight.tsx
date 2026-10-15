"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity UI "Spotlight" (spotlight-new). Two banks of angled light fall
 * from the top corners and sway slowly toward each other.
 *
 * Adapted: the stock blue hsla() beams are mixed from --ink instead, so the
 * light is white on obsidian and a faint graphite wash on the light theme.
 */
const beam = (pct: number) => `color-mix(in srgb, var(--ink) ${pct}%, transparent)`;

const GRADIENT_FIRST = `radial-gradient(68.54% 68.72% at 55.02% 31.46%, ${beam(8)} 0, ${beam(2)} 50%, transparent 80%)`;
const GRADIENT_SECOND = `radial-gradient(50% 50% at 50% 50%, ${beam(6)} 0, ${beam(2)} 80%, transparent 100%)`;
const GRADIENT_THIRD = `radial-gradient(50% 50% at 50% 50%, ${beam(4)} 0, ${beam(2)} 80%, transparent 100%)`;

export function Spotlight({
  className,
  translateY = -350,
  width = 560,
  height = 1380,
  smallWidth = 240,
  duration = 7,
  xOffset = 100,
}: {
  className?: string;
  translateY?: number;
  width?: number;
  height?: number;
  smallWidth?: number;
  duration?: number;
  xOffset?: number;
}) {
  const sway = (dir: 1 | -1) => ({
    animate: { x: [0, dir * xOffset, 0] },
    transition: {
      duration,
      repeat: Infinity,
      repeatType: "reverse" as const,
      ease: "easeInOut" as const,
    },
  });

  return (
    <motion.div
      aria-hidden
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 1.5 }}
      className={cn(
        "pointer-events-none absolute inset-0 h-full w-full overflow-hidden",
        className
      )}
    >
      <motion.div
        {...sway(1)}
        className="pointer-events-none absolute top-0 left-0 h-screen w-screen"
      >
        <div
          style={{
            transform: `translateY(${translateY}px) rotate(-45deg)`,
            background: GRADIENT_FIRST,
            width,
            height,
          }}
          className="absolute top-0 left-0"
        />
        <div
          style={{
            transform: "rotate(-45deg) translate(5%, -50%)",
            background: GRADIENT_SECOND,
            width: smallWidth,
            height,
          }}
          className="absolute top-0 left-0 origin-top-left"
        />
        <div
          style={{
            transform: "rotate(-45deg) translate(-180%, -70%)",
            background: GRADIENT_THIRD,
            width: smallWidth,
            height,
          }}
          className="absolute top-0 left-0 origin-top-left"
        />
      </motion.div>

      <motion.div
        {...sway(-1)}
        className="pointer-events-none absolute top-0 right-0 h-screen w-screen"
      >
        <div
          style={{
            transform: `translateY(${translateY}px) rotate(45deg)`,
            background: GRADIENT_FIRST,
            width,
            height,
          }}
          className="absolute top-0 right-0"
        />
        <div
          style={{
            transform: "rotate(45deg) translate(-5%, -50%)",
            background: GRADIENT_SECOND,
            width: smallWidth,
            height,
          }}
          className="absolute top-0 right-0 origin-top-right"
        />
        <div
          style={{
            transform: "rotate(45deg) translate(180%, -70%)",
            background: GRADIENT_THIRD,
            width: smallWidth,
            height,
          }}
          className="absolute top-0 right-0 origin-top-right"
        />
      </motion.div>
    </motion.div>
  );
}
