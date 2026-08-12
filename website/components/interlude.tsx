"use client";

import { Parallax } from "@/components/ui/parallax";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { useEngraving } from "@/lib/use-engraving";

/**
 * Deterministic PRNG so the starfield is identical on the server and the
 * client. Generating it in an effect (the previous approach) meant a render
 * pass with no stars, plus a setState the moment the component mounted.
 */
function mulberry32(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const STARS = (() => {
  const rand = mulberry32(0x0b5d17a);
  return Array.from({ length: 110 }, () => ({
    left: rand() * 100,
    top: rand() * 100,
    char: rand() < 0.12 ? "+" : ".",
    opacity: 0.15 + rand() * 0.5,
  }));
})();

/**
 * Full-bleed monochrome interlude: a sparse character starfield drifting
 * behind a single centered claim, breaking the container rhythm between the
 * two feature chapters.
 */
export function Interlude() {
  const { ref, art } = useEngraving<HTMLDivElement>("olympus");

  return (
    <section
      ref={ref}
      className="relative overflow-hidden border-t border-rule"
    >
      <MeanderDivider />
      <div aria-hidden className="absolute inset-0 font-mono text-[11px]">
        {STARS.map((s, i) => (
          <span
            key={i}
            className="absolute text-ink"
            style={{ left: `${s.left}%`, top: `${s.top}%`, opacity: s.opacity }}
          >
            {s.char}
          </span>
        ))}
      </div>
      {/* Olympus stands as a static engraved watermark, drifting slightly
          against the quote for depth. */}
      <Parallax offset={-14} className="pointer-events-none absolute inset-0">
        <pre
          aria-hidden
          className="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 font-mono select-none text-[4px] leading-[4.5px] text-ink opacity-[0.55]"
        >
          {art}
        </pre>
      </Parallax>
      <Parallax offset={20} className="relative z-10">
        <Reveal className="mx-auto max-w-4xl px-5 py-28 text-center lg:py-36">
          {/* Opaque ink on the claim so the denser watermark never
              competes with the headline. */}
          <p className="font-display text-[clamp(1.9rem,3.6vw,3rem)] leading-snug font-light text-ink">
            Where toil belongs to the agents,
            <br />
            <span className="italic text-ink-soft">
              judgement ascends to Olympus.
            </span>
          </p>
        </Reveal>
      </Parallax>
    </section>
  );
}
