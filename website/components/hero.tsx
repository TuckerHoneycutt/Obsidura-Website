"use client";

import { useRef } from "react";
import Link from "next/link";
import {
  easeInOut,
  motion,
  useReducedMotion,
  useScroll,
  useTransform,
} from "motion/react";
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
 * is more. The plain-language account waits below the fold and rises
 * into place as the reader scrolls down to it.
 */
export function Hero() {
  // The cue has done its job once the reader starts scrolling.
  const { scrollY } = useScroll();
  const cueOpacity = useTransform(scrollY, [0, 160], [1, 0]);

  return (
    <section className="relative overflow-clip">
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

      <Discover />
    </section>
  );
}

/**
 * Below the fold, the three points pin to the screen as one block and
 * scrolling reveals them instead of moving past them. The block starts
 * hidden - transparent and softly blurred - and its focus is tied directly to the
 * scroll position: scrolling down brings it in, scrolling back up conceals
 * it again. The section is two screens tall to give the reveal its stretch
 * of scroll; after that the pin releases and the page carries on.
 *
 * `overflow-clip` on the hero (not `overflow-hidden`) is what lets the
 * sticky stage work - a hidden-overflow ancestor would trap it.
 */
function Discover() {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  // 0 when the section's top enters the bottom of the viewport, 1 when its
  // end reaches the bottom - so the stage pins at the halfway mark.
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end end"],
  });
  // Motion hands opacity and filter driven straight off useScroll to a
  // native ScrollTimeline, which mis-measures this pinned stage and stalls
  // with the block still hidden. Computing them from a function transform
  // keeps them on Motion's own scroll loop, alongside y.
  // Spread over most of the approach and eased at both ends, so the block
  // drifts into focus rather than snapping; the blur and travel are kept
  // light so it reads as a soft reveal and stays cheap to repaint.
  const reveal = useTransform(scrollYProgress, [0.2, 0.8], [0, 1], {
    ease: easeInOut,
  });
  const opacity = useTransform(() => reveal.get());
  const y = useTransform(() => (1 - reveal.get()) * 16);
  const filter = useTransform(() => `blur(${(1 - reveal.get()) * 4}px)`);

  if (reduce) {
    return (
      <div id="discover" ref={ref} className="flex justify-center px-5 pt-8 pb-24 lg:pb-32">
        <PointList />
      </div>
    );
  }

  return (
    <div id="discover" ref={ref} className="relative h-[200svh]">
      {/* The stage fills the viewport under the sticky nav (~4rem, ~5.5rem from md). */}
      <div className="sticky top-16 flex h-[calc(100svh-4rem)] items-center justify-center px-5 md:top-[5.5rem] md:h-[calc(100svh-5.5rem)]">
        <motion.div
          style={{ opacity, y, filter }}
          className="will-change-[opacity,transform,filter]"
        >
          <PointList />
        </motion.div>
      </div>
    </div>
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
