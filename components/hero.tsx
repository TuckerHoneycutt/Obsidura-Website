"use client";

import { motion, useScroll, useTransform } from "motion/react";
import { AsciiMark } from "@/components/ascii-mark";
import { FramePanel } from "@/components/ui/frame-panel";
import { Magnetic } from "@/components/ui/magnetic";
import { Spotlight } from "@/components/ui/spotlight";

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 26 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.8, ease: [0.21, 0.47, 0.32, 0.98] as const, delay },
});

export function Hero() {
  const { scrollY } = useScroll();
  // The ASCII panel drifts slower than the page for depth.
  const asciiY = useTransform(scrollY, [0, 800], [0, -56]);

  return (
    <section id="top" className="relative overflow-hidden">
      <Spotlight />
      <div className="relative mx-auto grid max-w-6xl gap-10 px-5 pt-20 pb-16 lg:grid-cols-[1.15fr_1fr] lg:items-center lg:gap-14 lg:pt-28">
        <div>
          <motion.p {...rise(0)} className="kicker mb-6 text-accent">
            Agentic backend as a service
          </motion.p>

          <motion.h1
            {...rise(0.1)}
            className="text-5xl leading-[1.04] font-light tracking-tight sm:text-6xl lg:text-7xl"
          >
            Agents that run
            <br />
            <span className="headline-emph">your operations.</span>
          </motion.h1>

          <motion.p
            {...rise(0.2)}
            className="mt-7 max-w-xl text-lg leading-relaxed text-ink-soft sm:text-xl"
          >
            Obsidura orchestrates fleets of agents through Yggdrasil, our
            orchestration suite rooted directly in your company backend.
            Agents read your systems of record, execute the work, and escalate
            to humans only when judgment is required.
          </motion.p>

          <motion.div {...rise(0.3)} className="mt-9 flex flex-wrap gap-4">
            <Magnetic>
              <a
                href="#deploy"
                className="kicker inline-block bg-accent px-5 py-3 !text-paper transition-colors hover:bg-ink"
              >
                Book a demo
              </a>
            </Magnetic>
            <Magnetic strength={0.15}>
              <a
                href="#platform"
                className="kicker inline-block border border-rule px-5 py-3 !text-ink-soft transition-colors hover:border-accent-deep hover:!text-ink"
              >
                How it works
              </a>
            </Magnetic>
          </motion.div>

          <motion.div {...rise(0.4)} className="mt-12">
            <FramePanel className="inline-block bg-paper-warm/40 px-4 py-3">
              <p className="kicker">
                now onboarding design partners &mdash; q3 2026
              </p>
            </FramePanel>
          </motion.div>
        </div>

        <motion.div {...rise(0.35)} style={{ y: asciiY }}>
          <AsciiMark />
        </motion.div>
      </div>

      <div className="relative mx-auto max-w-6xl px-5 pb-10">
        <p className="kicker animate-scroll-cue w-max">
          the roots run deep &darr;
        </p>
      </div>
    </section>
  );
}
