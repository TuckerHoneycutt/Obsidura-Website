"use client";

import Image from "next/image";
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
 * decode. So: the category in the kicker, the promise in the headline, and a
 * plain-language definition underneath - what the thing runs, on what, under
 * what constraint - before anyone is asked to click anything.
 *
 * The mark no longer sits beside the copy as an exhibit; it hangs faded
 * behind the whole column, and everything reads down the center over it.
 */
export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <Spotlight />

      {/* The watermark: the mark at hero scale, faint enough that the copy
          stays the foreground. logo-invert flips it for the dark paper. */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.4, ease: "easeOut", delay: 0.2 }}
        aria-hidden
        className="pointer-events-none absolute inset-0 flex items-center justify-center"
      >
        <Image
          src="/logo-mark.svg"
          alt=""
          width={718}
          height={718}
          unoptimized
          className="logo-invert h-[clamp(20rem,50vw,34rem)] w-auto opacity-10 select-none"
        />
      </motion.div>

      <div className="relative mx-auto flex max-w-6xl flex-col items-center px-5 pt-16 pb-16 text-center lg:pt-28 lg:pb-24">
        <motion.p {...rise(0)} className="kicker mb-7 !text-[13px] text-accent">
          obsidura pantheon &mdash; the data layer for agents
        </motion.p>

        <motion.h1
          {...rise(0.1)}
          className="font-display text-[clamp(2.1rem,4.6vw,3.8rem)] leading-[1.02] font-light tracking-tight"
        >
          Intelligent <span className="headline-emph">Infrastructure.</span>
        </motion.h1>

        <motion.p
          {...rise(0.2)}
          className="mt-8 max-w-2xl font-display text-[clamp(1.25rem,1.8vw,1.6rem)] leading-[1.45] text-ink-soft"
        >
          Obsidura builds intelligent infrastructure across all of a
          company&apos;s data sources. Our platform, Pantheon, aggregates
          that data into one governed layer and lets agents run across it,
          with every run permission-scoped and recorded.
        </motion.p>

        <motion.div
          {...rise(0.3)}
          className="mt-10 flex flex-wrap justify-center gap-4"
        >
          <Link
            href="/contact"
            className="kicker inline-block bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
          >
            Book a demo
          </Link>
          <Link
            href="/automations"
            transitionTypes={["nav-forward"]}
            className="kicker inline-block border border-accent-deep bg-paper px-6 py-3.5 !text-ink transition-colors hover:border-accent"
          >
            See what it runs &rarr;
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
