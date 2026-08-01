"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";

// Tight viewBox from the vectorized brand mark (public/logo-mark.svg).
const VIEW = 718;
const OX = 265;
const OY = 260;

// Shimmer dash pattern in normalized path units (pathLength="1"). The
// drift keyframe in globals.css advances the offset by exactly one
// period (DASH + GAP) so the loop is seamless.
const DASH = 0.02;
const GAP = 0.045;

/**
 * The Obsidura mark, traced live from its own vector geometry. The scale
 * texture is baked into the single brand path, so stroking that path IS
 * tracing the scales: an intro pass draws the full texture in, the fill
 * settles beneath it, and a drifting dash pattern keeps glints moving
 * along the scale edges - never outside the bounds of the mark itself.
 */
export function TracedMark() {
  const [d, setD] = useState<string | null>(null);
  const reduced = useReducedMotion();

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

  return (
    <div className="relative aspect-square w-full">
      <svg
        viewBox={`${OX} ${OY} ${VIEW} ${VIEW}`}
        className="h-full w-full select-none text-ink"
        aria-hidden
      >
        {d && (
          <>
            {/* The mark itself, surfacing as the trace completes. */}
            <motion.path
              d={d}
              fill="currentColor"
              fillRule="evenodd"
              initial={{ opacity: reduced ? 1 : 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 1.8, delay: 1.1, ease: "easeInOut" }}
            />
            {!reduced && (
              <>
                {/* Intro pass: the scale texture draws itself once. */}
                <motion.path
                  d={d}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1}
                  initial={{ pathLength: 0, opacity: 1 }}
                  animate={{ pathLength: 1, opacity: 0 }}
                  transition={{
                    pathLength: { duration: 2.8, ease: [0.5, 0, 0.2, 1] },
                    opacity: { duration: 1.4, delay: 2.8 },
                  }}
                />
                {/* Ongoing shimmer: paper-colored dashes drift along the
                    scale edges so the texture glints without ever leaving
                    the silhouette. Plain path: motion.path would hijack
                    the pathLength attribute for its own draw logic. */}
                <path
                  d={d}
                  fill="none"
                  stroke="var(--paper)"
                  strokeWidth={1.4}
                  pathLength={1}
                  strokeDasharray={`${DASH} ${GAP}`}
                  className="animate-scale-drift"
                />
              </>
            )}
          </>
        )}
      </svg>
    </div>
  );
}
