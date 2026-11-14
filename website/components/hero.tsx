"use client";

import Link from "next/link";
import { motion, useScroll, useTransform } from "motion/react";
import { HoverBorderGradient } from "@/components/ui/hover-border-gradient";
import { Spotlight } from "@/components/ui/spotlight";
import { Reveal } from "@/components/ui/reveal";

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 26 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.8, ease: [0.21, 0.47, 0.32, 0.98] as const, delay },
});

const POINTS = [
  "Obsidura unifies the entire software lifecycle, enabling businesses to create, deploy, customize, secure, and maintain applications across cloud, on-premises, and air-gapped environments.",
  "Our agent-native infrastructure connects applications, data, and AI models through a common backend with enforced permissions, automated maintenance, and comprehensive auditability - sensible defaults for all software.",
  "Built for security, compliance, and cost efficiency, Obsidura makes complex software infrastructure simple, scalable, and accessible.",
];

const NUMERALS = ["I", "II", "III"];

/**
 * The first screen is only the claim and one way in, with a cue that there
 * is more. The plain-language account waits below the fold and rises
 * into place as the reader scrolls down to it.
 */
export function Hero() {
  // The cue has done its job once the reader starts scrolling.
  const { scrollY } = useScroll();
  const cueOpacity = useTransform(scrollY, [0, 160], [1, 0]);

  return (
    <section className="relative overflow-hidden">
      <Spotlight />

      {/* First screen: fills the viewport under the sticky nav (~4rem, ~5.5rem from md). */}
      <div className="relative mx-auto flex min-h-[calc(100svh-4rem)] max-w-6xl md:min-h-[calc(100svh-5.5rem)] flex-col items-center justify-center px-5 py-16 text-center">
        <motion.h1
          {...rise(0)}
          className="font-display text-[clamp(2.4rem,5.4vw,5.25rem)] leading-[1.02] font-light tracking-tight"
        >
          The Unified Infrastructure for Software
        </motion.h1>

        <motion.div {...rise(0.15)} className="mt-12 flex flex-wrap justify-center gap-4">
          <HoverBorderGradient
            as={Link}
            href="/contact"
            duration={1.2}
            className="kicker px-6 py-3.5 !text-ink"
          >
            Book a demo
          </HoverBorderGradient>
        </motion.div>

        <motion.div {...rise(0.3)} className="mt-14">
          <motion.a
            href="#discover"
            style={{ opacity: cueOpacity }}
            className="kicker flex flex-col items-center gap-3 text-ink-mute transition-colors hover:text-ink"
          >
            Scroll to discover
            <span
              aria-hidden
              className="animate-scroll-cue block h-8 w-px bg-current"
            />
          </motion.a>
        </motion.div>
      </div>

      {/* The account itself: three points, set left with roman numerals
          hanging in their own column, each rising in as it's reached. */}
      <div
        id="discover"
        className="relative mx-auto flex max-w-6xl flex-col items-center px-5 pt-8 pb-24 lg:pb-32"
      >
        <ol className="flex max-w-2xl flex-col gap-10">
          {POINTS.map((text, i) => (
            <li key={text}>
              <Reveal className="grid grid-cols-[2.75rem_1fr] gap-x-4 sm:grid-cols-[3.5rem_1fr]">
                <span
                  aria-hidden
                  className="text-right font-display text-[clamp(1.25rem,1.8vw,1.6rem)] leading-[1.45] text-ink-faint"
                >
                  {NUMERALS[i]}.
                </span>
                <p className="font-display text-[clamp(1.25rem,1.8vw,1.6rem)] leading-[1.45] text-ink-soft">
                  {text}
                </p>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
