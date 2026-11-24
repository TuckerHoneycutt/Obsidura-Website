"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { HoverBorderGradient } from "@/components/ui/hover-border-gradient";
import { Spotlight } from "@/components/ui/spotlight";

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 26 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.8, ease: [0.21, 0.47, 0.32, 0.98] as const, delay },
});

/**
 * The first screen is only the claim and one way in, with a cue down to
 * the points and the film. It fills the screen under the nav (the nav is
 * 4rem on phones, 4.8125rem from md up).
 */
export function Lead({ next }: { next: string }) {
  return (
    <section className="relative overflow-clip">
      <Spotlight />
      <div className="relative mx-auto flex min-h-[calc(100svh-4rem)] max-w-6xl flex-col items-center justify-center px-5 text-center md:min-h-[calc(100svh-4.8125rem)]">
        <motion.h1
          {...rise(0)}
          className="font-display text-[clamp(2.4rem,5.4vw,5.25rem)] leading-[1.02] font-light tracking-tight"
        >
          The Unified Lifecycle for Software
        </motion.h1>

        <motion.div {...rise(0.15)} className="mt-12">
          <HoverBorderGradient
            as={Link}
            href="/contact"
            duration={1.2}
            className="kicker px-6 py-3.5 !text-ink"
          >
            Book a demo
          </HoverBorderGradient>
        </motion.div>

        <motion.a
          {...rise(0.3)}
          href={next}
          className="kicker mt-14 flex flex-col items-center gap-3 text-ink-mute transition-colors hover:text-ink"
        >
          Scroll to discover
          <span aria-hidden className="animate-scroll-cue block h-8 w-px bg-current" />
        </motion.a>
      </div>
    </section>
  );
}
