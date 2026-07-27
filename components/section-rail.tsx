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
      className="fixed top-1/2 left-7 z-40 hidden -translate-y-1/2 flex-col gap-5 xl:flex"
    >
      {SECTIONS.map((s, i) => {
        const isActive = active === s.id;
        return (
          <a
            key={s.id}
            href={`#${s.id}`}
            className="group flex items-center gap-3"
          >
            <span
              className={cn(
                "kicker !text-[13px] transition-colors",
                isActive
                  ? "!text-accent"
                  : "!text-ink-mute group-hover:!text-ink-soft"
              )}
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <span
              className={cn(
                "h-px transition-all duration-300",
                isActive ? "w-7 bg-accent" : "w-4 bg-rule group-hover:bg-ink-mute"
              )}
            />
            <span
              className={cn(
                "kicker !text-[13px] transition-opacity duration-300",
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
