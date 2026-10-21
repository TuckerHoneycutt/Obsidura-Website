"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

const DEFAULT_CHARSET =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-={}[];:,.<>/?";

function randomChar(charset: string) {
  return charset.charAt(Math.floor(Math.random() * charset.length));
}

/**
 * The first frame must be identical on the server and the client, so it is
 * derived from the text itself rather than rolled at random; the scramble
 * only turns random once the animation is running in the browser.
 */
function seededGibberish(text: string, charset: string) {
  return text
    .split("")
    .map((ch, i) =>
      ch === " " ? " " : charset.charAt((ch.charCodeAt(0) * 31 + i * 17) % charset.length)
    );
}

/**
 * Aceternity UI "Encrypted Text": the words arrive as cipher, then decrypt
 * left to right, one character at a time.
 *
 * Adapted: the starting cipher is deterministic (the stock version calls
 * Math.random() during render, which never hydrates cleanly), the real
 * words are given to screen readers once via sr-only text instead of the
 * invalid role="text", and reduced-motion readers see plain text.
 */
export function EncryptedText({
  text,
  className,
  revealDelayMs = 50,
  charset = DEFAULT_CHARSET,
  flipDelayMs = 50,
  encryptedClassName,
  revealedClassName,
}: {
  text: string;
  className?: string;
  revealDelayMs?: number;
  charset?: string;
  flipDelayMs?: number;
  encryptedClassName?: string;
  revealedClassName?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true });
  const reduceMotion = useReducedMotion();

  const [revealCount, setRevealCount] = useState(0);
  const [scramble, setScramble] = useState(() => seededGibberish(text, charset));

  useEffect(() => {
    if (!isInView) return;
    // Reduced motion: skip the cipher and show the word on the next frame.
    // (Not at render - the server cannot know the preference, so the first
    // client render has to match its cipher markup.)
    if (reduceMotion) {
      const frame = requestAnimationFrame(() => setRevealCount(text.length));
      return () => cancelAnimationFrame(frame);
    }

    const start = performance.now();
    let lastFlip = start;
    let frame = 0;
    let cancelled = false;

    const update = (now: number) => {
      if (cancelled) return;
      const count = Math.min(
        text.length,
        Math.floor((now - start) / Math.max(1, revealDelayMs))
      );
      setRevealCount(count);
      if (count >= text.length) return;

      if (now - lastFlip >= Math.max(0, flipDelayMs)) {
        setScramble(
          text.split("").map((ch, i) =>
            i < count || ch === " " ? ch : randomChar(charset)
          )
        );
        lastFlip = now;
      }
      frame = requestAnimationFrame(update);
    };

    frame = requestAnimationFrame(update);
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, [isInView, reduceMotion, text, revealDelayMs, charset, flipDelayMs]);

  if (!text) return null;

  return (
    <span ref={ref} className={cn(className)}>
      <span className="sr-only">{text}</span>
      <span aria-hidden>
        {text.split("").map((char, index) => {
          const isRevealed = index < revealCount;
          return (
            <span
              key={index}
              className={cn(isRevealed ? revealedClassName : encryptedClassName)}
            >
              {isRevealed ? char : scramble[index]}
            </span>
          );
        })}
      </span>
    </span>
  );
}
