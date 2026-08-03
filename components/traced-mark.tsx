"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";

// Tight viewBox from the vectorized brand mark (public/logo-mark.svg).
const VIEW = 718;
const OX = 265;
const OY = 260;

// Shimmer dash pattern in normalized path units (pathLength="1"). The
// drift keyframe in globals.css advances the offset by exactly one
// period (DASH + GAP) so the loop is seamless.
const DASH = 0.02;
const GAP = 0.045;

// Whether the intro trace has already run during this page session.
// Module-level so it survives remounts (theme switches, client-side
// navigations); only a full page load resets it.
let introPlayed = false;

/**
 * The Obsidura mark, traced live from its own vector geometry. The scale
 * texture is baked into the single brand path, so stroking that path IS
 * tracing the scales: an intro pass draws the full texture in, the fill
 * settles beneath it, and a drifting dash pattern keeps glints moving
 * along the scale edges - never outside the bounds of the mark itself.
 *
 * All animation is CSS (trace-intro / mark-surface / animate-scale-drift
 * in globals.css) so the hidden starting states are resolved with the
 * first paint - script-driven SVG attributes can land a frame late in
 * some engines, flashing the finished mark. The intro plays exactly once
 * per page load: any later mount renders the mark already settled.
 */
export function TracedMark() {
  const [d, setD] = useState<string | null>(null);
  // Captured once at mount, before the effect below flips the flag.
  const [skipIntro] = useState(() => introPlayed);
  const reduced = useReducedMotion();

  useEffect(() => {
    introPlayed = true;
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/logo-mark.svg")
      .then((res) => res.text())
      .then((text) => {
        if (cancelled) return;
        const doc = new DOMParser().parseFromString(text, "image/svg+xml");
        const path = doc.querySelector("path");
        if (path) setD(path.getAttribute("d"));
      })
      .catch(() => {
        // Leave the panel empty rather than crash the hero; the mark
        // still appears in the nav and footer.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const still = reduced || skipIntro;

  return (
    <div className="relative aspect-square w-full">
      <svg
        viewBox={`${OX} ${OY} ${VIEW} ${VIEW}`}
        className="h-full w-full select-none text-ink"
        aria-hidden
      >
        {d && (
          <>
            {/* The mark itself, surfacing as the trace completes - or
                rendered settled when the intro already ran. */}
            <path
              d={d}
              fill="currentColor"
              fillRule="evenodd"
              className={still ? undefined : "mark-surface"}
            />
            {!reduced && (
              <>
                {/* Intro pass: the scale texture draws itself once per
                    page load. */}
                {!skipIntro && (
                  <path
                    d={d}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={1}
                    pathLength={1}
                    className="trace-intro"
                  />
                )}
                {/* Ongoing shimmer: paper-colored dashes drift along the
                    scale edges so the texture glints without ever leaving
                    the silhouette. On a remount the negative delay skips
                    the drift-in fade so the glints are simply already
                    there. */}
                <path
                  d={d}
                  fill="none"
                  stroke="var(--paper)"
                  strokeWidth={1.4}
                  pathLength={1}
                  strokeDasharray={`${DASH} ${GAP}`}
                  className="animate-scale-drift"
                  style={
                    skipIntro ? { animationDelay: "0s, -5s" } : undefined
                  }
                />
              </>
            )}
          </>
        )}
      </svg>
    </div>
  );
}
