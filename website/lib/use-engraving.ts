"use client";

import { useEffect, useRef, useState } from "react";
import { ENGRAVINGS, type EngravingName } from "@/lib/engravings";

/**
 * Pull an engraving's art in its own chunk once its container nears the
 * viewport. Returns the ref to attach, the art (null until it lands), and the
 * line count so a caller can reserve height first.
 *
 * The generous root margin means the fetch normally resolves before the plate
 * is ever on screen, so the art appears to have been there all along.
 */
export function useEngraving<T extends HTMLElement>(
  name: EngravingName,
  rootMargin = "600px 0px"
) {
  const ref = useRef<T>(null);
  const [art, setArt] = useState<string | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        observer.disconnect();
        // Decorative: a failed chunk leaves the reserved space empty rather
        // than breaking the section around it.
        ENGRAVINGS[name].load().then(setArt, () => {});
      },
      { rootMargin }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [name, rootMargin]);

  return { ref, art, lines: ENGRAVINGS[name].lines };
}
