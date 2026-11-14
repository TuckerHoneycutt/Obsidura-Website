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
 * is more. Scrolling hands off from that lead to the plain-language account.
 *
 * One model at every width: the hero is a tall track holding a pinned stage
 * exactly the height of the visible area under the nav, and the lead and the
 * points share one spot on it. Scrolling the track plays the handoff in
 * place - the lead fades out, then the points fade in - and then the pin
 * releases and the page carries on. Scrolling back up reverses it.
 *
 * Screen bounds have one source of truth: the nav's measured height, which
 * useHeroScroll publishes as --nav-h for the stage's pin offset and height.
 * The track's length is in screen heights, so the handoff takes the same
 * share of a screen to scroll through on a phone as on a desktop.
 */
export function Hero() {
  const trackRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const { start, distance } = useHeroScroll(trackRef, stageRef, listRef);
  const { scrollY } = useScroll();

  // Function transforms keep these on Motion's own scroll loop (opacity
  // mapped straight off useScroll is handed to a native ScrollTimeline,
  // which proved unreliable here).
  const progress = useTransform(() =>
    clamp((scrollY.get() - start.get()) / distance.get())
  );
  // Back to back, since the layers overlap: the lead is gone by 40% of the
  // track, the points arrive from 50% to 82%, and the rest is a short hold.
  const leadOpacity = useTransform(() => 1 - clamp((progress.get() - 0.08) / 0.32));
  const pointsOpacity = useTransform(() => clamp((progress.get() - 0.5) / 0.32));
  // Whichever layer is hidden lets clicks through - the points sit on top,
  // so hidden they would otherwise swallow clicks on the button and the cue.
  const leadPointerEvents = useTransform(() =>
    leadOpacity.get() < 0.5 ? "none" : "auto"
  );
  const pointsPointerEvents = useTransform(() =>
    pointsOpacity.get() < 0.5 ? "none" : "auto"
  );

  // The cue scrolls to where the points have just fully arrived, so a click
  // and a hand scroll finish in the same state. Lenis catches in-page anchor
  // clicks on window (and ignores preventDefault), so the click is stopped
  // here, at React's root, before it can get there.
  const goToPoints = (e: MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const top = start.get() + distance.get() * 0.82;
    if (window.__lenis) window.__lenis.scrollTo(top);
    else {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top, behavior: reduce ? "auto" : "smooth" });
    }
  };

  return (
    <section className="relative overflow-clip">
      <Spotlight />

      {/* The track: one visible screen plus 0.6 screens of handoff scroll.
          The stage pins just under the nav and fills the rest of the screen;
          the lead and the points sit in the same grid cell on it. The
          --nav-h fallbacks match the nav until the real height is measured. */}
      <div ref={trackRef} className="h-[160svh]">
        <div
          ref={stageRef}
          className="sticky top-[var(--nav-h,4rem)] grid h-[calc(100svh-var(--nav-h,4rem))] place-items-center *:col-start-1 *:row-start-1 md:top-[var(--nav-h,4.8125rem)] md:h-[calc(100svh-var(--nav-h,4.8125rem))]"
        >
          <div className="relative mx-auto flex max-w-6xl flex-col items-center px-5 text-center">
            {/* Wrapped so the scroll fade sits on its own layer, separate
                from each element's entrance rise. */}
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
            style={{ opacity: pointsOpacity, pointerEvents: pointsPointerEvents }}
            className="flex justify-center px-5"
          >
            <PointList ref={listRef} />
          </motion.div>
        </div>
      </div>
    </section>
  );
}

const clamp = (v: number) => Math.min(Math.max(v, 0), 1);

/**
 * Measures the screen bounds the hero plays in, re-measured whenever the
 * layout changes - resizes, rotation, a phone's address bar showing or
 * hiding, the nav changing height, late-loading fonts:
 *
 *  - --nav-h: the nav's real height, published on the track for the
 *    stage's pin offset and height.
 *  - start / distance: the scroll range over which the stage is pinned.
 *  - the space after: the points are centred on the stage, so once the pin
 *    releases the room under them is half the stage's spare height - more
 *    than the section needs - and what follows is pulled up by half of it.
 */
function useHeroScroll(
  trackRef: RefObject<HTMLDivElement | null>,
  stageRef: RefObject<HTMLDivElement | null>,
  listRef: RefObject<HTMLOListElement | null>
) {
  const start = useMotionValue(0);
  const distance = useMotionValue(400);

  useEffect(() => {
    const track = trackRef.current;
    const stage = stageRef.current;
    const list = listRef.current;
    const header = document.querySelector("header");
    if (!track || !stage || !list) return;

    const measure = () => {
      const navHeight = header?.getBoundingClientRect().height ?? 64;
      track.style.setProperty("--nav-h", `${navHeight}px`);

      const trackTop = track.getBoundingClientRect().top + window.scrollY;
      start.set(Math.max(trackTop - navHeight, 0));
      distance.set(Math.max(track.offsetHeight - stage.offsetHeight, 1));

      const below = Math.max((stage.offsetHeight - list.offsetHeight) / 2, 0);
      track.style.marginBottom = `${-below / 2}px`;
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    observer.observe(track);
    if (header) observer.observe(header);
    window.addEventListener("resize", measure);
    document.fonts?.ready.then(measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [trackRef, stageRef, listRef, start, distance]);

  return { start, distance };
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
