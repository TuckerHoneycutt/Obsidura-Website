"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  motion,
  useMotionValueEvent,
  useScroll,
  useSpring,
  useTransform,
} from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity UI "Tracing Beam": a rail down the left of a long read, with
 * a bead of light that travels it as you scroll.
 *
 * Adapted: the cyan-violet light runs ink into gold leaf, the emerald
 * "start here" dot is ink, and the rail is measured with a ResizeObserver
 * (the stock version measures once on mount, so the rail comes up short
 * whenever fonts load late or the window is resized). The rail sits in the
 * left gutter from md up and steps aside on phones, where there is none.
 */
export function TracingBeam({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [svgHeight, setSvgHeight] = useState(0);
  const [started, setStarted] = useState(false);

  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });

  useMotionValueEvent(scrollYProgress, "change", (v) => setStarted(v > 0));

  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const measure = () => setSvgHeight(el.offsetHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const y1 = useSpring(
    useTransform(scrollYProgress, [0, 0.8], [50, svgHeight]),
    { stiffness: 500, damping: 90 }
  );
  const y2 = useSpring(
    useTransform(scrollYProgress, [0, 1], [50, svgHeight - 200]),
    { stiffness: 500, damping: 90 }
  );

  return (
    <div ref={ref} className={cn("relative mx-auto h-full w-full", className)}>
      <div aria-hidden className="absolute top-3 -left-20 hidden md:block">
        <div
          className={cn(
            "ml-[27px] flex h-4 w-4 items-center justify-center border border-rule bg-paper transition-shadow duration-200",
            !started && "shadow-[0_0_0_4px_var(--accent-pale)]"
          )}
        >
          <div
            className={cn(
              "h-2 w-2 border transition-colors duration-200",
              started ? "border-ink-mute bg-paper" : "border-ink bg-ink"
            )}
          />
        </div>
        <svg
          viewBox={`0 0 20 ${svgHeight}`}
          width="20"
          height={svgHeight}
          className="ml-4 block"
        >
          <path
            d={`M 1 0V -36 l 18 24 V ${svgHeight * 0.8} l -18 24V ${svgHeight}`}
            fill="none"
            style={{ stroke: "var(--rule)" }}
          />
          <path
            d={`M 1 0V -36 l 18 24 V ${svgHeight * 0.8} l -18 24V ${svgHeight}`}
            fill="none"
            stroke="url(#tracing-beam-gradient)"
            strokeWidth="1.25"
            className="motion-reduce:hidden"
          />
          <defs>
            <motion.linearGradient
              id="tracing-beam-gradient"
              gradientUnits="userSpaceOnUse"
              x1="0"
              x2="0"
              y1={y1}
              y2={y2}
            >
              <stop style={{ stopColor: "var(--ink)", stopOpacity: 0 }} />
              <stop style={{ stopColor: "var(--ink)" }} />
              <stop offset="0.325" style={{ stopColor: "var(--gilt)" }} />
              <stop
                offset="1"
                style={{ stopColor: "var(--gilt)", stopOpacity: 0 }}
              />
            </motion.linearGradient>
          </defs>
        </svg>
      </div>
      <div ref={contentRef}>{children}</div>
    </div>
  );
}
