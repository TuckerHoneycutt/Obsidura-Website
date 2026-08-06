/** Lenis instance attached by SmoothScroll for in-page section jumps. */
export type LenisLike = {
  scrollTo: (
    target: string | number | HTMLElement,
    options?: { offset?: number; immediate?: boolean }
  ) => void;
};

declare global {
  interface Window {
    __lenis?: LenisLike;
  }
}

const NAV_OFFSET = -64;

/**
 * Scroll to a homepage section hash without remounting the page. Next.js
 * Link to "/#runtime" while already on "/" soft-navigates and remounts the
 * whole homepage (heavy ASCII, motion, Lenis) - that is the lag between
 * Platform / Runtime / Deploy. Prefer this when pathname is already "/".
 */
export function scrollToSection(hash: string) {
  const id = hash.startsWith("#") ? hash.slice(1) : hash;
  const el = document.getElementById(id);
  if (!el) return;

  const next = `#${id}`;
  if (window.location.hash !== next) {
    window.history.pushState(null, "", next);
  }

  const lenis = window.__lenis;
  if (lenis) {
    lenis.scrollTo(el, { offset: NAV_OFFSET });
    return;
  }

  el.scrollIntoView({ behavior: "smooth", block: "start" });
}
