"use client";

import Link from "next/link";
import { motion, useScroll, useTransform } from "motion/react";
import { TracedMark } from "@/components/traced-mark";
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
  // The mark panel drifts slower than the page for depth.
  const markY = useTransform(scrollY, [0, 800], [0, -56]);

  return (
    <section id="top" className="relative overflow-hidden">
      <Spotlight />
      <div className="relative mx-auto grid max-w-6xl gap-10 px-5 pt-20 pb-16 lg:grid-cols-[1.15fr_1fr] lg:items-center lg:gap-14 lg:pt-28">
        <div>
          <motion.p {...rise(0)} className="kicker mb-6 text-accent">
            i &mdash; agentic backend as a service
          </motion.p>

          <motion.h1
            {...rise(0.1)}
            className="font-display text-[clamp(2.75rem,5.5vw,4.15rem)] leading-[1.06] font-light tracking-tight"
          >
            Backend-native agents,
            <br />
            <span className="headline-emph">auditable operations.</span>
          </motion.h1>

          <motion.p
            {...rise(0.2)}
            className="mt-7 max-w-xl font-mono text-sm leading-relaxed text-ink-soft"
          >
            Obsidura is an enterprise AI agent orchestration platform.
            Pantheon, our orchestration suite, connects agents directly to
            your databases, APIs, and business applications - running
            durable, auditable workflows that escalate to a human only when
            judgment is required. Deploy in our cloud, your private VPC, or
            on-premises.
          </motion.p>

          <motion.div {...rise(0.3)} className="mt-9 flex flex-wrap gap-4">
            <Magnetic>
              <Link
                href="/contact"
                className="kicker inline-block bg-accent px-5 py-3 !text-paper transition-colors hover:bg-ink-soft"
              >
                Book a demo
              </Link>
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

        <motion.div {...rise(0.35)} style={{ y: markY }}>
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

      <div className="relative mx-auto max-w-6xl px-5 pb-10">
        <p className="kicker animate-scroll-cue w-max">
          the pantheon stirs below &darr;
        </p>
      </div>
    </section>
  );
}
