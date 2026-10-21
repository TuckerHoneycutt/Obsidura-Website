"use client";

import { useRef, useState } from "react";
import { motion } from "motion/react";

/**
 * Aceternity UI "Text Hover Effect": oversized outlined lettering that
 * traces itself on, then glows wherever the pointer passes over it.
 *
 * Adapted: set in the house display serif instead of Helvetica, outlined
 * in --rule, and the rainbow reveal is ink into gold leaf. Decorative: the
 * caller supplies the real heading text separately.
 */
export function TextHoverEffect({
  text,
  duration,
}: {
  text: string;
  duration?: number;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hovered, setHovered] = useState(false);
  const [maskPosition, setMaskPosition] = useState({ cx: "50%", cy: "50%" });

  function track(clientX: number, clientY: number) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    setMaskPosition({
      cx: `${((clientX - rect.left) / rect.width) * 100}%`,
      cy: `${((clientY - rect.top) / rect.height) * 100}%`,
    });
  }

  const type = {
    x: "50%",
    y: "50%",
    textAnchor: "middle",
    dominantBaseline: "middle",
    strokeWidth: 0.3,
    fontSize: 72,
    fontWeight: 500,
    style: { fontFamily: "var(--font-display), serif", fill: "transparent" },
  } as const;

  return (
    <svg
      ref={svgRef}
      aria-hidden
      width="100%"
      height="100%"
      viewBox="0 0 300 100"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onMouseMove={(e) => track(e.clientX, e.clientY)}
      className="select-none"
    >
      <defs>
        <linearGradient id="textGradient" gradientUnits="userSpaceOnUse">
          {hovered && (
            <>
              <stop offset="0%" style={{ stopColor: "var(--ink)" }} />
              <stop offset="35%" style={{ stopColor: "var(--gilt)" }} />
              <stop offset="65%" style={{ stopColor: "var(--ink-soft)" }} />
              <stop offset="100%" style={{ stopColor: "var(--gilt)" }} />
            </>
          )}
        </linearGradient>
        <motion.radialGradient
          id="revealMask"
          gradientUnits="userSpaceOnUse"
          r="20%"
          initial={{ cx: "50%", cy: "50%" }}
          animate={maskPosition}
          transition={{ duration: duration ?? 0, ease: "easeOut" }}
        >
          <stop offset="0%" stopColor="white" />
          <stop offset="100%" stopColor="black" />
        </motion.radialGradient>
        <mask id="textMask">
          <rect x="0" y="0" width="100%" height="100%" fill="url(#revealMask)" />
        </mask>
      </defs>
      <text
        {...type}
        style={{ ...type.style, stroke: "var(--rule)", opacity: hovered ? 0.7 : 0 }}
      >
        {text}
      </text>
      <motion.text
        {...type}
        style={{ ...type.style, stroke: "var(--ink-faint)" }}
        initial={{ strokeDashoffset: 1000, strokeDasharray: 1000 }}
        animate={{ strokeDashoffset: 0, strokeDasharray: 1000 }}
        transition={{ duration: 4, ease: "easeInOut" }}
      >
        {text}
      </motion.text>
      <text {...type} stroke="url(#textGradient)" mask="url(#textMask)">
        {text}
      </text>
    </svg>
  );
}
