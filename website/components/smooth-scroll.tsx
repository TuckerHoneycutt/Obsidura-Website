"use client";

import { useEffect } from "react";
import Lenis from "lenis";
import "lenis/dist/lenis.css";
import "@/lib/scroll-to-section";

/**
 * Lenis-powered smooth scrolling: wheel and touch scrolling are eased, and
 * anchor clicks animate to their target. Disabled entirely when the user
 * prefers reduced motion.
 */
export function SmoothScroll() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    const lenis = new Lenis({
      duration: 1.1,
      anchors: {
        offset: -64, // clear the sticky nav
      },
    });
    // Exposed so the nav can pause it while the mobile panel is open.
    window.__lenis = lenis;

    let raf = requestAnimationFrame(function loop(time) {
      lenis.raf(time);
      raf = requestAnimationFrame(loop);
    });

    return () => {
      cancelAnimationFrame(raf);
      if (window.__lenis === lenis) delete window.__lenis;
      lenis.destroy();
    };
  }, []);

  return null;
}
