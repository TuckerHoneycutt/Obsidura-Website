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
 * is more. Scrolling hands off from that lead to the plain-language account:
 * the lead fades out while the points - hidden at the top - fade in, and
 * scrolling back up reverses it.
 *
 * The handoff is staged differently by width (see useHeroScroll):
 *  - md and up: the points sit just below the lead and the handoff runs
 *    over exactly the scroll it takes to bring them to reading position.
 *  - phones: that distance is a single flick, so instead the hero pins and
 *    the lead and points share one spot. Over ~0.6 screens of scroll the
 *    lead fades out, then the points fade in, then the pin releases.
 * Both start from the same frame (lead shown, points hidden), so nothing
 * flashes before the width is known.
 */
export function Hero() {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const { phone, start, distance } = useHeroScroll(wrapperRef, stageRef, listRef);
  const { scrollY } = useScroll();

  // Function transforms keep these on Motion's own scroll loop (opacity
  // mapped straight off useScroll is handed to a native ScrollTimeline,
  // which proved unreliable here).
  const progress = useTransform(() =>
    clamp((scrollY.get() - start.get()) / distance.get())
  );
  // Phones run the two fades back to back, since the layers overlap; wider
  // screens cross them, since the layers are stacked.
  const leadOpacity = useTransform(() =>
    phone.get() ? 1 - clamp((progress.get() - 0.08) / 0.32) : 1 - progress.get()
  );
  const pointsOpacity = useTransform(() =>
    phone.get() ? clamp((progress.get() - 0.5) / 0.32) : progress.get()
  );
  // Whichever layer is hidden lets taps through. On phones the layers share
  // a spot and the points sit on top, so a hidden points layer would
  // otherwise swallow taps on the button and the cue.
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
    const top = start.get() + distance.get() * (phone.get() ? 0.82 : 1);
    if (window.__lenis) window.__lenis.scrollTo(top);
    else {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top, behavior: reduce ? "auto" : "smooth" });
    }
  };

  return (
    <section className="relative overflow-clip">
      <Spotlight />

      {/* Phones: a tall track with a pinned, screen-high stage in which the
          lead and the points occupy the same grid cell. md and up: the
          track and stage dissolve into ordinary flow, lead above points. */}
      <div ref={wrapperRef} className="h-[160svh] md:h-auto">
        <div
          ref={stageRef}
          className="sticky top-16 grid h-[calc(100svh-4rem)] place-items-center *:col-start-1 *:row-start-1 md:static md:block md:h-auto"
        >
          <div className="relative mx-auto flex max-w-6xl flex-col items-center px-5 text-center md:pt-24 md:pb-12 lg:pt-36 lg:pb-16">
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
            className="flex justify-center px-5 md:pb-24 lg:pb-32"
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
 * Measures the scroll range the handoff plays over, re-measured whenever
 * the layout changes - resizes, rotation, a phone's address bar showing or
 * hiding, late-loading fonts.
 *
 *  - phones (below md): from where the stage pins to where it releases.
 *  - md and up: from the top to where the points reach reading position -
 *    centred under the sticky nav when they fit, or just below it if not.
 */
function useHeroScroll(
  wrapperRef: RefObject<HTMLDivElement | null>,
  stageRef: RefObject<HTMLDivElement | null>,
  listRef: RefObject<HTMLOListElement | null>
) {
  const phone = useMotionValue(0);
  const start = useMotionValue(0);
  const distance = useMotionValue(400);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    const stage = stageRef.current;
    const list = listRef.current;
    if (!wrapper || !stage || !list) return;
    const wide = window.matchMedia("(min-width: 48rem)");

    const measure = () => {
      const navHeight =
        document.querySelector("header")?.getBoundingClientRect().height ?? 64;
      const docTop = (el: Element) => el.getBoundingClientRect().top + window.scrollY;

      if (!wide.matches) {
        phone.set(1);
        start.set(Math.max(docTop(wrapper) - navHeight, 0));
        distance.set(Math.max(wrapper.offsetHeight - stage.offsetHeight, 1));
        // The points are centred in the stage, so once the pin releases the
        // space under them is half the stage's spare height - more than the
        // section needs. Pull what follows up by half of that space.
        const below = Math.max((stage.offsetHeight - list.offsetHeight) / 2, 0);
        wrapper.style.marginBottom = `${-below / 2}px`;
        return;
      }

      wrapper.style.marginBottom = "";
      phone.set(0);
      start.set(0);
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
      const listHeight = list.offsetHeight;
      const room = window.innerHeight - navHeight;
      const restTop =
        listHeight + 3 * rem <= room
          ? navHeight + (room - listHeight) / 2
          : navHeight + 1.5 * rem;
      distance.set(Math.max(docTop(list) - restTop, 1));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    observer.observe(wrapper);
    observer.observe(document.documentElement);
    window.addEventListener("resize", measure);
    wide.addEventListener("change", measure);
    document.fonts?.ready.then(measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      wide.removeEventListener("change", measure);
    };
  }, [wrapperRef, stageRef, listRef, phone, start, distance]);

  return { phone, start, distance };
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
