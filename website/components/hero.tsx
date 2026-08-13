"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { TracedMark } from "@/components/traced-mark";
import { FramePanel } from "@/components/ui/frame-panel";
import { Magnetic } from "@/components/ui/magnetic";
import { Spotlight } from "@/components/ui/spotlight";

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 26 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.8, ease: [0.21, 0.47, 0.32, 0.98] as const, delay },
});

/**
 * The homepage no longer has five sections under it, so the claim carries the
 * whole screen: one statement at full size, one sentence of what the product
 * does, and the two things a visitor might actually want to do next.
 */
export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <Spotlight />
      {/* The claim gets the full measure - at this size it needs all 1152px
          to land on two lines instead of breaking mid-phrase. */}
      <div className="relative mx-auto max-w-6xl px-5 pt-16 lg:pt-24">
        <motion.p {...rise(0)} className="kicker mb-7 text-accent">
          obsidura &mdash; agentic backend as a service
        </motion.p>

        <motion.h1
          {...rise(0.1)}
          className="font-display text-[clamp(2.75rem,6.4vw,5.25rem)] leading-[1.02] font-light tracking-tight"
        >
          Backend-native agents,
          <br />
          <span className="headline-emph">auditable operations.</span>
        </motion.h1>
      </div>

      <div className="relative mx-auto grid max-w-6xl gap-10 px-5 pt-10 pb-16 lg:grid-cols-[1.1fr_1fr] lg:items-center lg:gap-14 lg:pb-24">
        <div>
          <motion.p
            {...rise(0.2)}
            className="max-w-xl font-display text-[clamp(1.25rem,1.8vw,1.6rem)] leading-[1.45] text-ink-soft"
          >
            One prompt in, a report back &mdash; drawn live from your
            databases, object stores, and internal APIs, and scoped to
            whoever asked.
          </motion.p>

          <motion.div {...rise(0.3)} className="mt-10 flex flex-wrap gap-4">
            <Magnetic>
              <Link
                href="/contact"
                className="kicker inline-block bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
              >
                Book a demo
              </Link>
            </Magnetic>
            <Magnetic strength={0.15}>
              <Link
                href="/reports"
                transitionTypes={["nav-forward"]}
                className="kicker inline-block border border-rule px-6 py-3.5 !text-ink-soft transition-colors hover:border-accent-deep hover:!text-ink"
              >
                See what it makes &rarr;
              </Link>
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

        <motion.div {...rise(0.35)}>
          {/* Museum mount: a sealed frame on warm paper with a faint gilt
              halo, so the mark reads as an exhibited artifact. */}
          <FramePanel className="bg-paper-warm/40">
            <div className="relative p-6 sm:p-10">
              <div
                aria-hidden
                className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,var(--gilt-glow),transparent_72%)]"
              />
              <TracedMark />
            </div>
          </FramePanel>
        </motion.div>
      </div>
    </section>
  );
}
