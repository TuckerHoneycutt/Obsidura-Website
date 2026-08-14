"use client";

import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useSpring } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * A hairline that draws itself down the left spine of its children as the
 * reader scrolls — the site's carved-line language applied to reading
 * progress. The static track is the rule; an ink line fills it as each
 * step passes the middle of the viewport. Desktop only: below lg the
 * spine column it traces does not exist.
 */
export function TracingRail({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 0.7", "end 0.7"],
  });
  const scaleY = useSpring(scrollYProgress, {
    stiffness: 120,
    damping: 30,
    restDelta: 0.001,
  });

  return (
    <div ref={ref} className={cn("relative", className)}>
      <div
        aria-hidden
        className="absolute top-0 bottom-0 left-[5px] hidden w-px bg-rule lg:block"
      />
      {!reduced && (
        <motion.div
          aria-hidden
          style={{ scaleY }}
          className="absolute top-0 bottom-0 left-[5px] hidden w-px origin-top bg-accent lg:block"
        />
      )}
      {children}
    </div>
  );
}
