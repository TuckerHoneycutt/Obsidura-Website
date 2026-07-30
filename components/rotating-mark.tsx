"use client";

import { useEffect, useId, useRef } from "react";

// Tight viewBox from the vectorized brand mark (public/logo-mark.svg).
const VIEW = 718;
const OX = 265;
const OY = 260;

// Radial amplitude field used to gate the displacement below: black (0) at
// the trunk, white (1) toward the tendril tips. Rendered once as a tiny
// data-URI image so the filter can read it via feImage.
const GATE_SVG = encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">` +
    `<defs><radialGradient id="g" cx="50%" cy="50%" r="62%">` +
    `<stop offset="0%" stop-color="black"/>` +
    `<stop offset="42%" stop-color="black"/>` +
    `<stop offset="100%" stop-color="white"/>` +
    `</radialGradient></defs>` +
    `<rect width="100" height="100" fill="url(#g)"/></svg>`
);
const GATE_HREF = `data:image/svg+xml,${GATE_SVG}`;

/**
 * The Obsidura mark, rendered once, with a single SVG filter that gently
 * warps it. Displacement amplitude is gated by a radial field so it is
 * zero at the trunk (perfectly still) and grows toward the tendril tips,
 * which slowly writhe as the underlying noise drifts.
 */
export function RotatingMark() {
  const reactId = useId().replace(/:/g, "");
  const filterId = `writhe-${reactId}`;
  const turbRef = useRef<SVGFETurbulenceElement>(null);

  useEffect(() => {
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    if (reduced) return;

    let raf = 0;
    const start = performance.now();

    const frame = (now: number) => {
      const t = (now - start) / 1000;
      // Slow drift so the noise field crawls rather than boils.
      const drift = t * 0.045;
      const fx = (0.009 + 0.003 * Math.sin(drift)).toFixed(4);
      const fy = (0.018 + 0.004 * Math.cos(drift * 0.8)).toFixed(4);
      turbRef.current?.setAttribute("baseFrequency", `${fx} ${fy}`);
      turbRef.current?.setAttribute(
        "seed",
        String(Math.floor(t * 4) % 1000)
      );

      raf = requestAnimationFrame(frame);
    };

    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="relative aspect-square w-full">
      <svg
        viewBox={`${OX} ${OY} ${VIEW} ${VIEW}`}
        className="h-full w-full select-none"
        aria-hidden
      >
        <defs>
          <filter
            id={filterId}
            x="-10%"
            y="-10%"
            width="120%"
            height="120%"
            colorInterpolationFilters="sRGB"
          >
            <feImage
              href={GATE_HREF}
              x="0%"
              y="0%"
              width="100%"
              height="100%"
              preserveAspectRatio="none"
              result="gate"
            />
            <feTurbulence
              ref={turbRef}
              type="fractalNoise"
              baseFrequency="0.009 0.018"
              numOctaves="2"
              seed="7"
              result="noise"
            />
            {/* Blend noise toward neutral gray (0.5 = no displacement)
                using the gate field, so amplitude fades to zero at the
                trunk without needing a second copy of the artwork. */}
            <feComposite
              in="noise"
              in2="gate"
              operator="arithmetic"
              k1="1"
              k2="0"
              k3="-0.5"
              k4="0.5"
              result="gatedNoise"
            />
            <feDisplacementMap
              in="SourceGraphic"
              in2="gatedNoise"
              scale="34"
              xChannelSelector="R"
              yChannelSelector="G"
            />
          </filter>
        </defs>

        <g className="logo-invert" filter={`url(#${filterId})`}>
          <image
            href="/logo-mark.svg"
            x={OX}
            y={OY}
            width={VIEW}
            height={VIEW}
            preserveAspectRatio="xMidYMid meet"
          />
        </g>
      </svg>
    </div>
  );
}
