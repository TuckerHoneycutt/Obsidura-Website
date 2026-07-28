"use client";

import { useEffect, useId, useRef } from "react";
import { FramePanel } from "@/components/ui/frame-panel";

// Tight viewBox from the vectorized brand mark (public/logo-mark.svg).
const VIEW = 718;
const OX = 265;
const OY = 260;
const CX = OX + VIEW / 2;
const CY = OY + VIEW / 2;

// Deterministic PRNG so the starfield renders identically on server and
// client without a hydration effect.
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(9);
const STARS = Array.from({ length: 46 }, () => ({
  left: rand() * 100,
  top: rand() * 100,
  opacity: 0.15 + rand() * 0.45,
}));

/**
 * Animated SVG specimen of the Obsidura mark.
 *
 * Artwork is the vectorized brand mark, so silhouette + scales stay faithful.
 * The mark spins slowly while a second copy of the same mesh drifts — the
 * interference makes the scales crawl along the arms, slower than a writhe
 * but clearly alive.
 */
export function RotatingMark() {
  const reactId = useId().replace(/:/g, "");
  const filterId = `scale-crawl-${reactId}`;
  const rotRef = useRef<SVGGElement>(null);
  const shimmerRef = useRef<SVGGElement>(null);
  const turbRef = useRef<SVGFETurbulenceElement>(null);
  const dispRef = useRef<SVGFEDisplacementMapElement>(null);

  useEffect(() => {
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    if (reduced) {
      rotRef.current?.setAttribute("transform", `rotate(8 ${CX} ${CY})`);
      return;
    }

    let raf = 0;
    const start = performance.now();

    const frame = (now: number) => {
      const t = (now - start) / 1000;

      // Whole mark: one turn every ~60s.
      rotRef.current?.setAttribute(
        "transform",
        `rotate(${((t / 60) * 360).toFixed(3)} ${CX} ${CY})`
      );

      // Scale crawl: a twin of the exact mesh orbits slowly. Dense braid
      // interference reads as scales sliding tipward — visible, not frantic.
      // ~18s per crawl cycle (was ~5s before).
      const crawlAngle = t * 0.35;
      const crawlRadius = 3.8;
      const ox = Math.sin(crawlAngle) * crawlRadius;
      const oy = Math.cos(crawlAngle * 0.85) * crawlRadius;
      const micro = Math.sin(t * 0.18) * 0.28;
      shimmerRef.current?.setAttribute(
        "transform",
        `translate(${ox.toFixed(3)} ${oy.toFixed(3)}) rotate(${micro.toFixed(3)} ${CX} ${CY})`
      );

      // Soft hide shiver — low amplitude, slow frequency.
      if (turbRef.current) {
        const fx = (0.008 + 0.002 * Math.sin(t * 0.2)).toFixed(4);
        const fy = (0.018 + 0.003 * Math.cos(t * 0.16)).toFixed(4);
        turbRef.current.setAttribute("baseFrequency", `${fx} ${fy}`);
        turbRef.current.setAttribute("seed", String(Math.floor(t * 1.2) % 500));
      }
      if (dispRef.current) {
        dispRef.current.setAttribute(
          "scale",
          (1.8 + 0.4 * Math.sin(t * 0.5)).toFixed(2)
        );
      }

      raf = requestAnimationFrame(frame);
    };

    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <FramePanel className="bg-paper-warm/40">
      <div className="flex items-center justify-between border-b border-rule px-4 py-2">
        <span className="kicker">yggdrasil core</span>
        <span className="kicker text-accent">live</span>
      </div>
      <div className="relative flex aspect-square items-center justify-center overflow-hidden">
        <div aria-hidden className="absolute inset-0 font-mono text-[10px]">
          {STARS.map((s, i) => (
            <span
              key={i}
              className="absolute text-ink"
              style={{
                left: `${s.left}%`,
                top: `${s.top}%`,
                opacity: s.opacity,
              }}
            >
              .
            </span>
          ))}
        </div>
        <svg
          viewBox={`${OX} ${OY} ${VIEW} ${VIEW}`}
          className="relative w-[72%] select-none"
          aria-hidden
        >
          <defs>
            <filter
              id={filterId}
              x="-6%"
              y="-6%"
              width="112%"
              height="112%"
              colorInterpolationFilters="sRGB"
            >
              <feTurbulence
                ref={turbRef}
                type="fractalNoise"
                baseFrequency="0.008 0.018"
                numOctaves="2"
                seed="3"
                result="noise"
              />
              <feDisplacementMap
                ref={dispRef}
                in="SourceGraphic"
                in2="noise"
                scale="1.8"
                xChannelSelector="R"
                yChannelSelector="G"
              />
            </filter>
          </defs>

          <g ref={rotRef} className="logo-invert" filter={`url(#${filterId})`}>
            <image
              href="/logo-mark.svg"
              x={OX}
              y={OY}
              width={VIEW}
              height={VIEW}
              preserveAspectRatio="xMidYMid meet"
            />
            {/* Twin mesh — the slow drift is what makes the scales crawl */}
            <g
              ref={shimmerRef}
              opacity={0.38}
              style={{ mixBlendMode: "soft-light" }}
            >
              <image
                href="/logo-mark.svg"
                x={OX}
                y={OY}
                width={VIEW}
                height={VIEW}
                preserveAspectRatio="xMidYMid meet"
              />
            </g>
          </g>
        </svg>
      </div>
      <div className="flex items-center justify-between border-t border-rule px-4 py-2">
        <span className="kicker">obsidura://yggdrasil.0</span>
        <span className="kicker">fig. 01</span>
      </div>
    </FramePanel>
  );
}
