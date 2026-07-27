"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { id: "top", label: "the crown" },
  { id: "platform", label: "the roots" },
  { id: "runtime", label: "the trunk" },
  { id: "deploy", label: "the realms" },
];

/**
 * Fixed index rail on wide screens: shows the current section number and
 * label, editorial style.
 */
export function SectionRail() {
  const [active, setActive] = useState("top");

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
      className="fixed top-1/2 left-5 z-40 hidden -translate-y-1/2 flex-col gap-4 xl:flex"
    >
      {SECTIONS.map((s, i) => {
        const isActive = active === s.id;
        return (
          <a
            key={s.id}
            href={`#${s.id}`}
            className="group flex items-center gap-2.5"
          >
            <span
              className={cn(
                "kicker !text-[10px] transition-colors",
                isActive ? "!text-accent" : "!text-ink-faint"
              )}
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <span
              className={cn(
                "h-px transition-all duration-300",
                isActive ? "w-6 bg-accent" : "w-3 bg-rule group-hover:bg-ink-mute"
              )}
            />
            <span
              className={cn(
                "kicker !text-[10px] transition-opacity duration-300",
                isActive ? "opacity-100" : "opacity-0 group-hover:opacity-60"
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
