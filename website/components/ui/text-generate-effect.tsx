"use client";

import { useEffect } from "react";
import { motion, stagger, useAnimate, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity UI "Text Generate Effect": words surface one after another,
 * each sharpening out of a blur.
 *
 * Adapted: renders as a single paragraph in whatever type the caller sets
 * (the stock version hard-codes bold 2xl black/white), the per-word stagger
 * is a prop so a long lede does not take nine seconds to arrive, and
 * reduced-motion readers get the finished text at once.
 */
export function TextGenerateEffect({
  words,
  className,
  filter = true,
  duration = 0.5,
  delay = 0,
  staggerBy = 0.2,
}: {
  words: string;
  className?: string;
  filter?: boolean;
  duration?: number;
  delay?: number;
  staggerBy?: number;
}) {
  const [scope, animate] = useAnimate();
  const reduceMotion = useReducedMotion();
  const wordsArray = words.split(" ");

  // The hidden start state is the same markup on the server and client;
  // only the animation differs, so reduced motion cannot cause a mismatch.
  useEffect(() => {
    animate(
      "span",
      { opacity: 1, filter: filter ? "blur(0px)" : "none" },
      reduceMotion
        ? { duration: 0 }
        : { duration, delay: stagger(staggerBy, { startDelay: delay }) }
    );
  }, [animate, reduceMotion, filter, duration, delay, staggerBy]);

  return (
    <p ref={scope} className={cn(className)}>
      {wordsArray.map((word, idx) => (
        <motion.span
          key={word + idx}
          style={{ opacity: 0, filter: filter ? "blur(10px)" : "none" }}
        >
          {word}{" "}
        </motion.span>
      ))}
    </p>
  );
}
