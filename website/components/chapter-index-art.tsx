"use client";

import { CHAR_RATIO, ENGRAVINGS, type EngravingName } from "@/lib/engravings";
import { useEngraving } from "@/lib/use-engraving";

/**
 * Width the ghost band is drawn at. Fluid, so the preview keeps its share of
 * the row as the frame widens; the font size is derived from it in CSS.
 */
const BAND_WIDTH = "clamp(18rem, 24vw, 28rem)";

/**
 * A chapter's engraving surfacing in its index row. The art is drawn at a
 * fluid width from its own grid and the row clips it to a horizontal band,
 * so what appears on hover reads as a strip of the plate waiting on the
 * chapter page - a preview, not a second exhibit. Faint by design: the
 * row's text keeps the foreground, and the vertical mask keeps the clipped
 * edges from reading as cuts.
 *
 * Below lg the band never lays out, so the observer never fires and the
 * art's chunk is never fetched on small screens.
 */
export function ChapterIndexArt({ name }: { name: EngravingName }) {
  const { ref, art } = useEngraving<HTMLDivElement>(name);
  const { cols } = ENGRAVINGS[name];
  const fontSize = `calc(${BAND_WIDTH} / ${(cols * CHAR_RATIO).toFixed(3)})`;

  return (
    <div
      ref={ref}
      aria-hidden
      style={{ width: BAND_WIDTH }}
      className="pointer-events-none absolute inset-y-0 right-10 hidden items-center justify-center overflow-hidden opacity-0 transition-opacity duration-500 group-hover:opacity-100 group-focus-visible:opacity-100 lg:flex [mask-image:linear-gradient(to_bottom,transparent,black_25%,black_75%,transparent)]"
    >
      <pre
        style={{ fontSize, lineHeight: 1 }}
        className="m-0 font-mono whitespace-pre select-none text-ink/20"
      >
        {art}
      </pre>
    </div>
  );
}
