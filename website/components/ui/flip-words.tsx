"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity UI "Flip Words": a phrase that cycles through alternatives,
 * each letter settling out of a blur and the outgoing one flung away.
 *
 * Adapted: the timer is cleared on unmount (the stock version leaks a
 * pending setTimeout), and colour comes from the caller rather than
 * neutral-900/100. The full list is offered to assistive tech once, so a
 * screen reader hears every option instead of whichever word is showing.
 */
export function FlipWords({
  words,
  duration = 3000,
  className,
}: {
  words: string[];
  duration?: number;
  className?: string;
}) {
  const [index, setIndex] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);
  const currentWord = words[index];

  useEffect(() => {
    if (isAnimating) return;
    const t = setTimeout(() => {
      setIndex((i) => (i + 1) % words.length);
      setIsAnimating(true);
    }, duration);
    return () => clearTimeout(t);
  }, [isAnimating, duration, words.length]);

  return (
    <>
      <span className="sr-only">{words.join(", ")}</span>
      <span aria-hidden>
        <AnimatePresence onExitComplete={() => setIsAnimating(false)}>
          <motion.span
            key={currentWord}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 100, damping: 10 }}
            exit={{
              opacity: 0,
              y: -40,
              x: 40,
              filter: "blur(8px)",
              scale: 2,
              position: "absolute",
            }}
            className={cn("relative z-10 inline-block text-left", className)}
          >
            {currentWord.split(" ").map((word, wordIndex) => (
              <motion.span
                key={word + wordIndex}
                initial={{ opacity: 0, y: 10, filter: "blur(8px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                transition={{ delay: wordIndex * 0.3, duration: 0.3 }}
                className="inline-block whitespace-nowrap"
              >
                {word.split("").map((letter, letterIndex) => (
                  <motion.span
                    key={word + letterIndex}
                    initial={{ opacity: 0, y: 10, filter: "blur(8px)" }}
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    transition={{
                      delay: wordIndex * 0.3 + letterIndex * 0.05,
                      duration: 0.2,
                    }}
                    className="inline-block"
                  >
                    {letter}
                  </motion.span>
                ))}
                <span className="inline-block">&nbsp;</span>
              </motion.span>
            ))}
          </motion.span>
        </AnimatePresence>
      </span>
    </>
  );
}
