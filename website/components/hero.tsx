"use client";

import Link from "next/link";
import { motion, useScroll, useTransform } from "motion/react";
import { HoverBorderGradient } from "@/components/ui/hover-border-gradient";
import { Spotlight } from "@/components/ui/spotlight";

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
 * is more; the plain-language account follows directly beneath.
 */
export function Hero() {
  // One handoff over the first 160px of scroll: the claim, the button and
  // the cue fade out while the points - sitting just below, but hidden at
  // the top - fade in, so they seem to arrive from further down the page.
  // Back at the top it all reverses. Function transforms keep these on
  // Motion's own scroll loop (opacity mapped straight off useScroll is
  // handed to a native ScrollTimeline, which proved unreliable here).
  const { scrollY } = useScroll();
  const handoff = useTransform(() =>
    Math.min(Math.max(scrollY.get() / 160, 0), 1)
  );
  const pointsOpacity = useTransform(() => handoff.get());
  const leadOpacity = useTransform(() => 1 - handoff.get());
  // A hidden button shouldn't still catch clicks.
  const leadPointerEvents = useTransform(() =>
    handoff.get() > 0.5 ? "none" : "auto"
  );

  return (
    <section className="relative overflow-clip">
      <Spotlight />

      <div className="relative mx-auto flex max-w-6xl flex-col items-center px-5 pt-24 pb-12 text-center lg:pt-36 lg:pb-16">
        {/* Wrapped so the scroll fade sits on its own layer, separate from
            each element's entrance rise. */}
        <motion.div
          style={{ opacity: leadOpacity, pointerEvents: leadPointerEvents }}
          className="flex flex-col items-center"
        >
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
        </motion.div>

        <motion.div {...rise(0.3)} className="mt-14">
          <motion.a
            href="#discover"
            style={{ opacity: leadOpacity, pointerEvents: leadPointerEvents }}
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
          hanging in their own column, hidden until the reader scrolls. */}
      <motion.div
        style={{ opacity: pointsOpacity }}
        className="relative flex justify-center px-5 pb-24 lg:pb-32"
      >
        {/* The cue's anchor sits a little above the list: anchor jumps land
            their target 4rem from the top, which on desktop is under the
            taller nav and clipped the first line. Raising the target, not
            padding the list, keeps the layout itself unchanged. */}
        <span id="discover" aria-hidden className="absolute -top-2 md:-top-14" />
        <PointList />
      </motion.div>
    </section>
  );
}

function PointList() {
  return (
    <ol className="flex max-w-2xl flex-col gap-6 sm:gap-10">
      {POINTS.map((text, i) => (
        <li
          key={text}
          className="grid grid-cols-[2.75rem_1fr] gap-x-4 sm:grid-cols-[3.5rem_1fr]"
        >
          <span
            aria-hidden
            className="text-right font-display text-[clamp(1.25rem,1.8vw,1.6rem)] leading-[1.45] text-ink-faint"
          >
            {NUMERALS[i]}.
          </span>
          <p className="font-display text-[clamp(1.25rem,1.8vw,1.6rem)] leading-[1.45] text-ink-soft">
            {text}
          </p>
        </li>
      ))}
    </ol>
  );
}
