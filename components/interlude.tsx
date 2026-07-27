"use client";

import { useEffect, useState } from "react";
import { Parallax } from "@/components/ui/parallax";
import { Reveal } from "@/components/ui/reveal";
import { RuneDivider } from "@/components/ui/rune-mark";

type Star = {
  left: number;
  top: number;
  char: string;
  opacity: number;
};

/**
 * Full-bleed monochrome interlude: a sparse character starfield drifting
 * behind a single centered claim, breaking the container rhythm between the
 * two feature chapters.
 */
export function Interlude() {
  // Generated client-side only, so SSR and hydration markup match.
  const [stars, setStars] = useState<Star[]>([]);

  useEffect(() => {
    setStars(
      Array.from({ length: 110 }, () => ({
        left: Math.random() * 100,
        top: Math.random() * 100,
        char: Math.random() < 0.12 ? "+" : ".",
        opacity: 0.15 + Math.random() * 0.5,
      }))
    );
  }, []);

  return (
    <section className="relative overflow-hidden border-t border-rule">
      <RuneDivider />
      <div aria-hidden className="absolute inset-0 font-mono text-[11px]">
        {stars.map((s, i) => (
          <span
            key={i}
            className="absolute text-ink"
            style={{ left: `${s.left}%`, top: `${s.top}%`, opacity: s.opacity }}
          >
            {s.char}
          </span>
        ))}
      </div>
      {/* Original ASCII rendering of Yggdrasil: crown, trunk, and roots */}
      <pre
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 font-mono text-[9px] leading-[12px] text-ink opacity-[0.13] select-none sm:text-[11px] sm:leading-[14px]"
      >
        {String.raw`          *    .   *   .    *
      .    \   |   |   /    .
        *__ \_ \ | | / _/ __*
           \__\ \\|// /__/
          __   \\\|///   __
            \___\\|//___/
             ___ \|/ ___
            /   \_|_/   \
                  |
                  |
                  |
                  |
             ____/|\____
            /   / | \   \
         __/  /  /|\  \  \__
        /    /  / | \  \    \
       .    /  /  |  \  \    .
          .   /   |   \   .
             .    |    .`}
      </pre>
      <Parallax offset={20} className="relative">
        <Reveal className="mx-auto max-w-4xl px-5 py-28 text-center lg:py-36">
          <p className="font-display text-[clamp(1.9rem,3.6vw,3rem)] leading-snug font-light">
            The routine stays at the roots.
            <br />
            <span className="italic text-ink-soft">
              Only judgment rises to the crown.
            </span>
          </p>
        </Reveal>
      </Parallax>
    </section>
  );
}
