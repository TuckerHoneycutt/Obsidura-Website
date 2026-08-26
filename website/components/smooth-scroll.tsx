"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import Lenis from "lenis";
import "lenis/dist/lenis.css";
import "@/lib/scroll-to-section";

/**
 * Lenis-powered smooth scrolling: wheel and touch scrolling are eased, and
 * anchor clicks animate to their target. Disabled entirely when the user
 * prefers reduced motion.
 */
export function SmoothScroll() {
  const pathname = usePathname();
  const firstRender = useRef(true);
  const poppedState = useRef(false);

  // The router resets window scroll on navigation, but Lenis's animated
  // position still holds the old page's offset and its next frame writes it
  // back - so a page opened from partway down another page lands partway
  // down too. Snapping Lenis itself to the top keeps the two in agreement.
  // Back/forward and hash targets are left alone so the browser's own
  // restoration and the anchor handling keep working.
  useEffect(() => {
    const onPop = () => {
      poppedState.current = true;
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    if (poppedState.current) {
      poppedState.current = false;
      return;
    }
    if (window.location.hash) return;
    window.__lenis?.scrollTo(0, { immediate: true });
  }, [pathname]);

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
