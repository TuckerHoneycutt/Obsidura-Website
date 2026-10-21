"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { BackgroundBeams } from "@/components/ui/background-beams";
import { HoverBorderGradient } from "@/components/ui/hover-border-gradient";
import { Spotlight } from "@/components/ui/spotlight";
import { TextGenerateEffect } from "@/components/ui/text-generate-effect";

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 26 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.8, ease: [0.21, 0.47, 0.32, 0.98] as const, delay },
});

const LEDE =
  "Small software gives companies and teams the freedom to build purpose-built tools for their unique use cases. What was once difficult to deploy, secure, and share becomes seamless. Pantheon, our infrastructure engine, gives agents everything they need to build, deploy, and run software across your organization.";

/**
 * The claim carries the screen, but it has to be a claim a stranger can
 * decode. So: the promise in the headline, and a plain-language account
 * underneath - what small software is, why the big clouds fail it, and what
 * powers ours - before anyone is asked to click anything.
 *
 * Light falls on it from both corners (Spotlight) over a sheaf of slow
 * threads (Background Beams); the lede writes itself in word by word.
 */
export function Hero() {
  return (
    // Solid paper here: the body's dot grain and the beam lines fought
    // each other, so the hero hides the grain and keeps the beams alone.
    <section className="relative overflow-hidden bg-paper">
      <BackgroundBeams className="opacity-70 [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_75%)]" />
      <Spotlight />

      <div className="relative mx-auto flex max-w-6xl flex-col items-center px-5 pt-28 pb-16 text-center lg:pt-44 lg:pb-24">
        <motion.h1
          {...rise(0)}
          className="font-display text-[clamp(2.4rem,5.4vw,5.25rem)] leading-[1.02] font-light tracking-tight"
        >
          A Cloud for <span className="text-accent">Small Software</span>
        </motion.h1>

        <TextGenerateEffect
          words={LEDE}
          delay={0.35}
          staggerBy={0.025}
          duration={0.6}
          className="mt-8 max-w-2xl font-display text-[clamp(1.25rem,1.8vw,1.6rem)] leading-[1.45] text-ink-soft"
        />

        <motion.div {...rise(0.9)} className="mt-16 flex flex-wrap justify-center gap-4">
          <HoverBorderGradient
            as={Link}
            href="/contact"
            duration={1.2}
            className="kicker px-6 py-3.5 !text-ink"
          >
            Book a demo
          </HoverBorderGradient>
        </motion.div>
      </div>
    </section>
  );
}
