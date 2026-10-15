"use client";

import { useEffect, useRef, useState, type ReactNode, type SVGProps } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity UI "Pointer Highlight": a hairline box draws itself around a
 * phrase while a cursor rides its corner, as if someone were marking it up.
 *
 * Adapted: built from spans so it can sit inside a heading (the stock
 * divs are invalid in an h1), the observer is disconnected properly on
 * unmount, and the box and pointer are ink rather than blue.
 */
export function PointerHighlight({
  children,
  rectangleClassName,
  pointerClassName,
  containerClassName,
}: {
  children: ReactNode;
  rectangleClassName?: string;
  pointerClassName?: string;
  containerClassName?: string;
}) {
  const containerRef = useRef<HTMLSpanElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setDimensions({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <span
      ref={containerRef}
      className={cn("relative inline-block w-fit", containerClassName)}
    >
      {children}
      {dimensions.width > 0 && dimensions.height > 0 && (
        <motion.span
          aria-hidden
          className="pointer-events-none absolute inset-0 z-0 block"
          initial={{ opacity: 0, scale: 0.95, originX: 0, originY: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          <motion.span
            className={cn(
              "absolute inset-0 block border border-ink-mute",
              rectangleClassName
            )}
            initial={{ width: 0, height: 0 }}
            whileInView={{ width: dimensions.width, height: dimensions.height }}
            viewport={{ once: true }}
            transition={{ duration: 1, ease: "easeInOut" }}
          />
          <motion.span
            className="pointer-events-none absolute block"
            initial={{ opacity: 0 }}
            whileInView={{
              opacity: 1,
              x: dimensions.width + 4,
              y: dimensions.height + 4,
            }}
            viewport={{ once: true }}
            style={{ rotate: -90 }}
            transition={{
              opacity: { duration: 0.1, ease: "easeInOut" },
              duration: 1,
              ease: "easeInOut",
            }}
          >
            <Pointer className={cn("h-5 w-5 text-ink", pointerClassName)} />
          </motion.span>
        </motion.span>
      )}
    </span>
  );
}

function Pointer(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      stroke="currentColor"
      fill="currentColor"
      strokeWidth="1"
      strokeLinecap="round"
      strokeLinejoin="round"
      viewBox="0 0 16 16"
      height="1em"
      width="1em"
      {...props}
    >
      <path d="M14.082 2.182a.5.5 0 0 1 .103.557L8.528 15.467a.5.5 0 0 1-.917-.007L5.57 10.694.803 8.652a.5.5 0 0 1-.006-.916l12.728-5.657a.5.5 0 0 1 .556.103z" />
    </svg>
  );
}
