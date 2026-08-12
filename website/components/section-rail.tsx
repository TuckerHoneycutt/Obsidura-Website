"use client";

import { useEffect, useState } from "react";
import { motion, useScroll } from "motion/react";
import { cn, romanNumeral } from "@/lib/utils";

const SECTIONS = [
  { id: "top", label: "olympus" },
  { id: "reports", label: "the artifacts" },
  { id: "definitions", label: "the labors" },
  { id: "governance", label: "the ledger" },
  { id: "runtime", label: "the forge" },
  { id: "deploy", label: "the dominions" },
];

/**
 * Fixed index rail on wide screens: shows the current section number and
 * label, editorial style.
 */
export function SectionRail() {
  const [active, setActive] = useState("top");
  const { scrollYProgress } = useScroll();

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: "-40% 0px -55% 0px" }
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  return (
    <nav
      aria-label="Sections"
      className="fixed top-1/2 left-5 z-40 hidden -translate-y-1/2 flex-col gap-3.5 xl:flex"
    >
      {/* The descent from Olympus: a hairline that fills with scroll. */}
      <span
        aria-hidden
        className="absolute -left-3 top-0 h-full w-px bg-rule"
      >
        <motion.span
          className="absolute inset-0 origin-top bg-accent"
          style={{ scaleY: scrollYProgress }}
        />
      </span>
      {SECTIONS.map((s, i) => {
        const isActive = active === s.id;
        return (
          <a
            key={s.id}
            href={`#${s.id}`}
            className="group flex items-center gap-2"
          >
            <span
              className={cn(
                "kicker w-5 text-right !text-[11px] transition-colors",
                isActive
                  ? "!text-accent"
                  : "!text-ink-mute group-hover:!text-ink-soft"
              )}
            >
              {romanNumeral(i + 1)}
            </span>
            <span
              className={cn(
                "h-px transition-all duration-300",
                isActive ? "w-5 bg-accent" : "w-3 bg-rule group-hover:bg-ink-mute"
              )}
            />
            <span
              className={cn(
                "kicker !text-[11px] transition-opacity duration-300",
                isActive
                  ? "!text-ink opacity-100"
                  : "!text-ink-soft opacity-0 group-hover:opacity-80"
              )}
            >
              {s.label}
            </span>
          </a>
        );
      })}
    </nav>
  );
}
