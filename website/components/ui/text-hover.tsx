"use client";

import { useId, useRef } from "react";
import { cn } from "@/lib/utils";

/*
 * Geometry in viewBox units. The font size equals the viewBox height, so the
 * SVG set at a given CSS height draws its letters at that font size - the
 * same sizing contract as a leading-none line of text. The baseline sits
 * where the cap height (~0.64em in Cormorant) centers in the box, so the
 * word centers optically beside the mark rather than on its em box.
 */
const FONT_SIZE = 100;
const BASELINE = 82;
const PAD = 4;
/** Glyph advances plus ~0.1em tracking, with slack; lengthAdjust="spacing"
    spends any difference on the gaps, never on the letterforms. */
const LENGTH = 580;
const WIDTH = LENGTH + PAD * 2;
/** Radius of the pool of light, in viewBox units - a little over two letters. */
const LAMP = 150;

/**
 * Aceternity-style text hover effect, carved rather than lit: the word is
 * cut into the paper as a hairline outline, and a pool of ink follows the
 * pointer through it, gilt at the center. The footer is the one place on
 * the homepage the sacred color is spent, and only where the reader looks.
 *
 * Without a fine pointer, or with reduced motion, the outline carries a
 * quiet solid fill instead so the lockup still reads as a word.
 */
export function TextHover({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  // useId returns characters that break a url(#...) reference; keep it to
  // a plain token.
  const id = useId().replace(/[^\w-]/g, "");
  const svgRef = useRef<SVGSVGElement>(null);
  const lampRef = useRef<SVGRadialGradientElement>(null);
  const revealRef = useRef<SVGGElement>(null);

  // Written straight to the gradient's attributes: a React state update per
  // pointer move would re-render the whole wordmark sixty times a second.
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.pointerType !== "mouse") return;
    const ctm = svgRef.current?.getScreenCTM();
    if (!ctm) return;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    lampRef.current?.setAttribute("cx", String(p.x));
    lampRef.current?.setAttribute("cy", String(p.y));
    revealRef.current?.style.setProperty("opacity", "1");
  };

  const leave = () => revealRef.current?.style.setProperty("opacity", "0");

  const word = (props: React.SVGProps<SVGTextElement>) => (
    <text
      x={PAD}
      y={BASELINE}
      textLength={LENGTH}
      lengthAdjust="spacing"
      fontSize={FONT_SIZE}
      fontWeight={300}
      style={{ fontFamily: "var(--font-display), serif" }}
      {...props}
    >
      {text.toUpperCase()}
    </text>
  );

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${WIDTH} ${FONT_SIZE}`}
      role="img"
      aria-label={text}
      onPointerMove={move}
      onPointerLeave={leave}
      className={cn("block w-auto overflow-visible select-none", className)}
    >
      <defs>
        <radialGradient
          ref={lampRef}
          id={`${id}-lamp`}
          gradientUnits="userSpaceOnUse"
          cx={WIDTH / 2}
          cy={FONT_SIZE / 2}
          r={LAMP}
        >
          <stop offset="0%" style={{ stopColor: "var(--gilt)" }} />
          <stop offset="28%" style={{ stopColor: "var(--ink)" }} />
          <stop
            offset="100%"
            style={{ stopColor: "var(--ink)", stopOpacity: 0 }}
          />
        </radialGradient>
      </defs>

      {/* The carving: a hairline that stays a hairline at every size. The
          fill is the fallback for touch and reduced motion only. */}
      {word({
        vectorEffect: "non-scaling-stroke",
        strokeWidth: 1,
        className:
          "fill-ink-mute stroke-ink-faint pointer-fine:motion-safe:fill-transparent",
      })}

      <g
        ref={revealRef}
        aria-hidden
        style={{ opacity: 0 }}
        className="pointer-events-none transition-opacity duration-500 motion-reduce:hidden"
      >
        {word({
          fill: `url(#${id}-lamp)`,
          stroke: `url(#${id}-lamp)`,
          vectorEffect: "non-scaling-stroke",
          strokeWidth: 1,
        })}
      </g>
    </svg>
  );
}
