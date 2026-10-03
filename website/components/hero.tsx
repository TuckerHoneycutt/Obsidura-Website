"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { Spotlight } from "@/components/ui/spotlight";

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 26 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.8, ease: [0.21, 0.47, 0.32, 0.98] as const, delay },
});

/**
 * The claim carries the screen, but it has to be a claim a stranger can
 * decode. So: the promise in the headline, and a plain-language account
 * underneath - what small software is, why the big clouds fail it, and what
 * powers ours - before anyone is asked to click anything.
 */
export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <Spotlight />

      <div className="relative mx-auto flex max-w-6xl flex-col items-center px-5 pt-16 pb-16 text-center lg:pt-28 lg:pb-24">
        <motion.h1
          {...rise(0)}
          className="font-display text-[clamp(2.4rem,5.4vw,5.25rem)] leading-[1.02] font-light tracking-tight"
        >
          A Cloud for <span className="headline-emph">Small Software.</span>
        </motion.h1>

        <motion.p
          {...rise(0.1)}
          className="mt-8 max-w-2xl font-display text-[clamp(1.25rem,1.8vw,1.6rem)] leading-[1.45] text-ink-soft"
        >
          Agents have made small software &mdash; purpose-built tools for one
          person or one team &mdash; easy to build, but the incumbent clouds
          were designed for big software, and deploying and sharing it is
          still hard. Obsidura is a cloud designed for small software,
          powered by our engine, Pantheon: it runs your tools in a secure,
          governed environment and makes sharing one with a colleague as
          easy as sharing a doc.
        </motion.p>

        <motion.div
          {...rise(0.2)}
          className="mt-10 flex flex-wrap justify-center gap-4"
        >
          <Link
            href="/contact"
            className="kicker inline-block bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
          >
            Book a demo
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
