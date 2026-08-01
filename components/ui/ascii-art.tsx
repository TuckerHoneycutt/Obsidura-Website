"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * ASCII art that chisels itself in when scrolled into view: characters
 * surface in random order, each appearing first as a faint point before
 * settling into its final glyph - like an inscription being cut into
 * stone. Renders the full art on the server so layout never shifts;
 * reduced-motion users simply see it static.
 */
export function AsciiArt({
  art,
  className,
  duration = 2200,
}: {
  art: string;
  className?: string;
  duration?: number;
}) {
  const ref = useRef<HTMLPreElement>(null);
  const [text, setText] = useState(art);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    if (reduced) return;

    // Per-character reveal order; whitespace needs no carving.
    const thresholds = Array.from(art, (ch) =>
      ch === " " || ch === "\n" ? -1 : Math.random()
    );
    const blank = art.replace(/[^\n]/g, " ");

    let raf = 0;
    const carve = () => {
      const t0 = performance.now();
      const frame = (now: number) => {
        const p = Math.min((now - t0) / duration, 1);
        let out = "";
        for (let i = 0; i < art.length; i++) {
          const t = thresholds[i];
          if (t <= p - 0.07) out += art[i];
          else if (t <= p) out += "\u00b7";
          else out += art[i] === "\n" ? "\n" : " ";
        }
        setText(p >= 1 ? art : out);
        if (p < 1) raf = requestAnimationFrame(frame);
      };
      raf = requestAnimationFrame(frame);
    };

    // Hide until first seen, then carve once.
    setText(blank);
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          io.disconnect();
          carve();
        }
      },
      { threshold: 0.2 }
    );
    io.observe(el);

    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [art, duration]);

  return (
    <pre ref={ref} aria-hidden className={cn("select-none", className)}>
      {text}
    </pre>
  );
}
