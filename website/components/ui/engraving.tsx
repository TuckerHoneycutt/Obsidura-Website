"use client";

import { CHAR_RATIO, ENGRAVINGS, type EngravingName } from "@/lib/engravings";
import { useEngraving } from "@/lib/use-engraving";
import { cn } from "@/lib/utils";

/**
 * An engraving at the size it was drawn for.
 *
 * These were cut on a character grid - 157 columns of Herakles, 170 of
 * Olympus - and shrinking them into 3px plates threw away most of what was
 * drawn. So the type size is derived from the art's own grid instead of
 * picked: at `100cqw / (cols * CHAR_RATIO)` the drawing lands exactly on the
 * container's width, whatever that width turns out to be. The second term
 * caps it by the height budget, since the 110-line pieces are portrait and
 * would otherwise run past a screen and a half.
 *
 * Everything follows from those two numbers, so there is nothing to retune
 * per breakpoint and no JS in the sizing path.
 */
export function Engraving({
  name,
  /** Tallest the art may get, in px. The width fit wins when it is smaller. */
  maxHeight = 620,
  className,
  dim = false,
}: {
  name: EngravingName;
  maxHeight?: number;
  className?: string;
  dim?: boolean;
}) {
  const { ref, art } = useEngraving<HTMLDivElement>(name);
  const { lines, cols } = ENGRAVINGS[name];

  const widthFit = `${(100 / (cols * CHAR_RATIO)).toFixed(4)}cqw`;
  const heightFit = `${(maxHeight / lines).toFixed(3)}px`;

  return (
    <div
      ref={ref}
      aria-hidden
      // The container is what cqw resolves against, so the art tracks
      // whatever column it is dropped into.
      style={{ containerType: "inline-size", minHeight: maxHeight }}
      className={cn("flex items-center justify-center", className)}
    >
      <pre
        style={{
          fontSize: `min(${widthFit}, ${heightFit})`,
          lineHeight: 1,
        }}
        className={cn(
          "m-0 font-mono whitespace-pre select-none",
          dim ? "text-ink opacity-55" : "text-ink"
        )}
      >
        {art}
      </pre>
    </div>
  );
}
