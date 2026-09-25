"use client";

import { motion, useReducedMotion, type Variants } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity-style text generate, in the log's own cadence: when the panel
 * scrolls in, its lines print one after another rather than the block
 * fading up whole. Every line is in the DOM from the first render - only
 * hidden until the panel is seen - so the copy is there for search and
 * assistive tech either way. Plays once.
 *
 * Lines register with the nearest panel through motion's variant context,
 * so a LogLine can sit inside plain wrappers (or server components) and
 * still take its place in the sequence.
 */
export function LogReveal({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  const panel: Variants = {
    hidden: {},
    visible: {
      transition: reduced
        ? { staggerChildren: 0 }
        : { delayChildren: 0.15, staggerChildren: 0.08 },
    },
  };

  return (
    <motion.div
      className={cn(className)}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
      variants={panel}
    >
      {children}
    </motion.div>
  );
}

/**
 * One printed line. It wipes on left to right as it fades, the way output
 * lands in a terminal; the clip is dropped once it finishes so underlines
 * and descenders are never cut.
 */
export function LogLine({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  const line: Variants = {
    hidden: { opacity: 0, clipPath: "inset(0 100% 0 0)" },
    visible: {
      opacity: 1,
      clipPath: "inset(0 0% 0 0)",
      transitionEnd: { clipPath: "none" },
      transition: reduced
        ? { duration: 0 }
        : { duration: 0.24, ease: [0.21, 0.47, 0.32, 0.98] },
    },
  };

  return (
    <motion.div className={cn(className)} variants={line}>
      {children}
    </motion.div>
  );
}
