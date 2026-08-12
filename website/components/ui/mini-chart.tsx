"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/*
 * Miniature marks for the report previews on the homepage. These stand in
 * for the charts a rendered report carries, so they follow the same mark
 * rules as a real chart rather than being loose decoration: one series in
 * one colour, hairline solid axes, 4px rounded data-ends square at the
 * baseline, 2px lines, markers ringed in the surface colour, and no value
 * printed on every point.
 *
 * The readout replaces the caption on hover instead of floating a tooltip
 * over the card: at this size a tooltip would cover the very marks it
 * describes, and a caption line cannot be clipped by the card edge.
 *
 * Strokes use non-scaling-stroke so a hairline stays a hairline no matter
 * how far the card scales the viewBox up.
 */

const W = 220;
const H = 60;
const BASE = 50;
const TOP = 8;

/** Column with square corners at the baseline and a 2px-equivalent radius on the data end. */
function columnPath(x: number, y: number, w: number, r = 2) {
  // A column shorter than its own radius degrades to a plain rectangle.
  const radius = Math.min(r, (BASE - y) / 2);
  return [
    `M${x},${BASE}`,
    `V${y + radius}`,
    `Q${x},${y} ${x + radius},${y}`,
    `H${x + w - radius}`,
    `Q${x + w},${y} ${x + w},${y + radius}`,
    `V${BASE}`,
    "Z",
  ].join(" ");
}

function Caption({
  caption,
  readout,
}: {
  caption: string;
  readout: string | null;
}) {
  return (
    <p className="kicker mt-1.5 !text-[9px] truncate">
      {readout ? <span className="!text-ink">{readout}</span> : caption}
    </p>
  );
}

export function MiniColumns({
  values,
  labels,
  caption,
  unit = "",
  className,
}: {
  values: number[];
  labels: string[];
  caption: string;
  unit?: string;
  className?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...values);
  const slot = W / values.length;
  // Cap the bar so the band always keeps some air; the leftover is the gap.
  const width = Math.min(14, slot - 5);

  return (
    <div className={className}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        aria-hidden
        className="block w-full"
        onMouseLeave={() => setHover(null)}
      >
        {values.map((v, i) => {
          const y = BASE - (v / max) * (BASE - TOP);
          const x = i * slot + (slot - width) / 2;
          return (
            <path
              key={i}
              d={columnPath(x, y, width)}
              className={cn(
                "fill-ink transition-opacity",
                hover !== null && hover !== i && "opacity-35"
              )}
            />
          );
        })}
        <line
          x1="0"
          y1={BASE}
          x2={W}
          y2={BASE}
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
          className="stroke-rule"
        />
        {/* Hit targets span the whole band, not just the mark, so a 14px
            column is not something you have to land on precisely. */}
        {values.map((_, i) => (
          <rect
            key={i}
            x={i * slot}
            y={0}
            width={slot}
            height={H}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>
      <Caption
        caption={caption}
        readout={
          hover === null ? null : `${labels[hover]} · ${values[hover]}${unit}`
        }
      />
    </div>
  );
}

export function MiniLine({
  values,
  labels,
  caption,
  unit = "",
  /** Index of the one point worth calling out - drawn ringed, not labelled. */
  flag,
  className,
}: {
  values: number[];
  labels: string[];
  caption: string;
  unit?: string;
  flag?: number;
  className?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const step = W / (values.length - 1);
  const points = values.map((v, i) => {
    const x = i * step;
    const y = BASE - ((v - min) / span) * (BASE - TOP);
    return [x, y] as const;
  });
  const last = points[points.length - 1];
  const flagged = flag !== undefined ? points[flag] : undefined;
  const hovered = hover !== null ? points[hover] : undefined;

  return (
    <div className={className}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        aria-hidden
        className="block w-full"
        onMouseLeave={() => setHover(null)}
      >
        <line
          x1="0"
          y1={BASE}
          x2={W}
          y2={BASE}
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
          className="stroke-rule"
        />
        <polyline
          points={points.map(([x, y]) => `${x},${y}`).join(" ")}
          fill="none"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
          className="stroke-ink"
        />
        {/* The anomaly: ringed in the surface colour so it reads where it
            crosses the trace, rather than labelled with a number. */}
        {flagged && (
          <circle
            cx={flagged[0]}
            cy={flagged[1]}
            r="4"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
            className="fill-paper stroke-ink"
          />
        )}
        <circle
          cx={last[0]}
          cy={last[1]}
          r="4"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
          className="fill-ink stroke-paper"
        />
        {hovered && (
          <>
            <line
              x1={hovered[0]}
              y1={TOP - 4}
              x2={hovered[0]}
              y2={BASE}
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
              className="stroke-ink-faint"
            />
            <circle
              cx={hovered[0]}
              cy={hovered[1]}
              r="4"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
              className="fill-ink stroke-paper"
            />
          </>
        )}
        {values.map((_, i) => (
          <rect
            key={i}
            x={i * step - step / 2}
            y={0}
            width={step}
            height={H}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>
      <Caption
        caption={caption}
        readout={
          hover === null ? null : `${labels[hover]} · ${values[hover]}${unit}`
        }
      />
    </div>
  );
}

/**
 * A stat tile: label above, figure below. The figure sits in the mono face -
 * the site's machine voice - and keeps proportional figures, since a lone
 * number set in tabular digits reads loose at this size.
 */
export function MiniStat({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="kicker !text-[9px] truncate">{label}</p>
      <p className="mt-1 font-mono text-[15px] leading-none text-ink">
        {value}
      </p>
    </div>
  );
}
