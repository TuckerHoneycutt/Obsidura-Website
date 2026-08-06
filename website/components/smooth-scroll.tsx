"use client";

import { useEffect } from "react";
import Lenis from "lenis";
import "lenis/dist/lenis.css";
import "@/lib/scroll-to-section";

/**
 * Lenis-powered smooth scrolling. Wheel and touch scrolling are eased, and
 * in-page anchor clicks (nav, CTAs, section rail) animate to their target.
 * Disabled entirely when the user prefers reduced motion.
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
    // Exposed for same-page nav section jumps (see scrollToSection).
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
