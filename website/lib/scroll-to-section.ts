/** Lenis instance attached by SmoothScroll, used for the nav's scroll lock. */
export type LenisLike = {
  scrollTo: (
    target: string | number | HTMLElement,
    options?: { offset?: number; immediate?: boolean }
  ) => void;
  /** Pausing the loop is the only way to lock scroll while a panel is open -
   *  overflow:hidden on body does not stop Lenis driving the page. */
  stop?: () => void;
  start?: () => void;
};

declare global {
  interface Window {
    __lenis?: LenisLike;
  }
}
