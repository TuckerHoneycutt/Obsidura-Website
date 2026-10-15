"use client";

import { memo } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity UI "Background Beams": a sheaf of fine curves with light
 * running along them.
 *
 * Adapted: the cyan-to-violet gradient is drawn in ink and the grey ground
 * net in --rule, so the beams read as silk threads in either theme. The
 * stock component rolls Math.random() on every render; here each beam's
 * timing comes from a fixed hash of its index, so the server and client
 * agree and a re-render does not reshuffle the light.
 */

// Each beam is the previous one shifted 7 units right and 8 units up.
const PATHS = Array.from({ length: 50 }, (_, i) => {
  const x = -380 + i * 7;
  const y = -189 - i * 8;
  return `M${x} ${y}C${x} ${y} ${x + 68} ${y + 405} ${x + 532} ${y + 532}C${x + 996} ${y + 659} ${x + 1064} ${y + 1064} ${x + 1064} ${y + 1064}`;
});

const GROUND = Array.from({ length: 58 }, (_, i) => {
  const x = -380 + i * 7;
  const y = -189 - i * 8;
  return `M${x} ${y}C${x} ${y} ${x + 68} ${y + 405} ${x + 532} ${y + 532}C${x + 996} ${y + 659} ${x + 1064} ${y + 1064} ${x + 1064} ${y + 1064}`;
}).join("");

/** Deterministic 0..1 value per index (a cheap integer hash). */
function seeded(i: number, salt: number) {
  const n = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453;
  return n - Math.floor(n);
}

export const BackgroundBeams = memo(function BackgroundBeams({
  className,
}: {
  className?: string;
}) {
  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-0 flex h-full w-full items-center justify-center",
        className
      )}
    >
      <svg
        className="absolute z-0 h-full w-full"
        width="100%"
        height="100%"
        viewBox="0 0 696 316"
        fill="none"
        preserveAspectRatio="xMidYMid slice"
      >
        <path
          d={GROUND}
          stroke="url(#beams-ground)"
          strokeOpacity="0.08"
          strokeWidth="0.5"
        />

        {PATHS.map((d, i) => (
          <path
            key={i}
            d={d}
            stroke={`url(#beam-${i})`}
            strokeOpacity="0.5"
            strokeWidth="0.5"
          />
        ))}

        <defs>
          {PATHS.map((_, i) => (
            <motion.linearGradient
              id={`beam-${i}`}
              key={i}
              initial={{ x1: "0%", x2: "0%", y1: "0%", y2: "0%" }}
              animate={{
                x1: ["0%", "100%"],
                x2: ["0%", "95%"],
                y1: ["0%", "100%"],
                y2: ["0%", `${93 + seeded(i, 1) * 8}%`],
              }}
              transition={{
                duration: seeded(i, 2) * 10 + 10,
                ease: "easeInOut",
                repeat: Infinity,
                delay: seeded(i, 3) * 10,
              }}
            >
              <stop style={{ stopColor: "var(--ink)", stopOpacity: 0 }} />
              <stop style={{ stopColor: "var(--ink)" }} />
              <stop offset="32.5%" style={{ stopColor: "var(--ink-mute)" }} />
              <stop
                offset="100%"
                style={{ stopColor: "var(--ink-faint)", stopOpacity: 0 }}
              />
            </motion.linearGradient>
          ))}

          <radialGradient
            id="beams-ground"
            cx="0"
            cy="0"
            r="1"
            gradientUnits="userSpaceOnUse"
            gradientTransform="translate(352 34) rotate(90) scale(555 1560.62)"
          >
            <stop offset="0.0666667" style={{ stopColor: "var(--ink-soft)" }} />
            <stop offset="0.243243" style={{ stopColor: "var(--ink-soft)" }} />
            <stop
              offset="0.43594"
              style={{ stopColor: "var(--ink-soft)", stopOpacity: 0 }}
            />
          </radialGradient>
        </defs>
      </svg>
    </div>
  );
});
