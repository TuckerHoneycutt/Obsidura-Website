"use client";

import { useEffect, useRef, type MouseEvent, type Ref, type RefObject } from "react";
import Link from "next/link";
import {
  motion,
  useMotionValue,
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
 * is more; the plain-language account follows directly beneath.
 */
export function Hero() {
  // One handoff: the claim, the button and the cue fade out while the
  // points - sitting just below, but hidden at the top - fade in, so they
  // seem to arrive from further down the page. Back at the top it all
  // reverses. The handoff runs over exactly the scroll it takes to bring
  // the points to their reading position (see useRestingScroll), so on any
  // screen the lead is gone just as the points settle - no dead gap where
  // the faded lead still holds its space. Function transforms keep these
  // on Motion's own scroll loop (opacity mapped straight off useScroll is
  // handed to a native ScrollTimeline, which proved unreliable here).
  const listRef = useRef<HTMLOListElement>(null);
  const restingScroll = useRestingScroll(listRef);
  const { scrollY } = useScroll();
  const handoff = useTransform(() =>
    Math.min(Math.max(scrollY.get() / restingScroll.get(), 0), 1)
  );
  const pointsOpacity = useTransform(() => handoff.get());
  const leadOpacity = useTransform(() => 1 - handoff.get());
  // A hidden button shouldn't still catch clicks.
  const leadPointerEvents = useTransform(() =>
    handoff.get() > 0.5 ? "none" : "auto"
  );

  // The cue scrolls to the same resting point the handoff is measured to,
  // so a click and a hand scroll finish in the same state. Lenis catches
  // in-page anchor clicks on window (and ignores preventDefault), so the
  // click is stopped here, at React's root, before it can get there.
  const goToPoints = (e: MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const top = restingScroll.get();
    if (window.__lenis) window.__lenis.scrollTo(top);
    else {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top, behavior: reduce ? "auto" : "smooth" });
    }
  };

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
            onClick={goToPoints}
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
        id="discover"
        style={{ opacity: pointsOpacity }}
        className="flex justify-center px-5 pb-24 lg:pb-32"
      >
        <PointList ref={listRef} />
      </motion.div>
    </section>
  );
}

/**
 * How far the page must scroll to bring the points to their reading
 * position: centred under the sticky nav when they fit on screen, or just
 * below it when they're taller (small phones). Re-measured whenever the
 * list or viewport changes size - resizes, rotation, a phone's address bar
 * showing or hiding, late-loading fonts.
 */
function useRestingScroll(listRef: RefObject<HTMLOListElement | null>) {
  const resting = useMotionValue(400);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;

    const measure = () => {
      const navHeight =
        document.querySelector("header")?.getBoundingClientRect().height ?? 64;
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
      const listTop = list.getBoundingClientRect().top + window.scrollY;
      const listHeight = list.offsetHeight;
      const room = window.innerHeight - navHeight;
      const restTop =
        listHeight + 3 * rem <= room
          ? navHeight + (room - listHeight) / 2
          : navHeight + 1.5 * rem;
      resting.set(Math.max(listTop - restTop, 1));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    observer.observe(document.documentElement);
    window.addEventListener("resize", measure);
    document.fonts?.ready.then(measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [listRef, resting]);

  return resting;
}

// Phones get a step-down in size and spacing so the three points fit on
// one screen; from sm up the sizes are unchanged.
const pointText =
  "font-display text-[1.0625rem] leading-[1.45] sm:text-[clamp(1.25rem,1.8vw,1.6rem)]";

function PointList({ ref }: { ref?: Ref<HTMLOListElement> }) {
  return (
    <ol ref={ref} className="flex max-w-2xl flex-col gap-5 sm:gap-10">
      {POINTS.map((text, i) => (
        <li
          key={text}
          className="grid grid-cols-[2rem_1fr] gap-x-3 sm:grid-cols-[3.5rem_1fr] sm:gap-x-4"
        >
          <span aria-hidden className={`text-right text-ink-faint ${pointText}`}>
            {NUMERALS[i]}.
          </span>
          <p className={`text-ink-soft ${pointText}`}>{text}</p>
        </li>
      ))}
    </ol>
  );
}
