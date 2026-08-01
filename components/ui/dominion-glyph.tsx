import { cn } from "@/lib/utils";

export type Dominion = "zeus" | "poseidon" | "hades";

// Each brother's emblem, drawn with the same hairline square-cap strokes
// as the meander motif: Zeus's thunderbolt, Poseidon's trident, and the
// bident of Hades.
const PATHS: Record<Dominion, string> = {
  zeus: "M13 2 6 13h5l-2 9 9-11h-5l2-9z",
  poseidon:
    "M12 22V4M9.5 6.5 12 4l2.5 2.5M6 5v5c0 2.8 2.4 4 6 4m6-9v5c0 2.8-2.4 4-6 4",
  hades: "M12 22v-8.5M7 4v5c0 3 2.2 4.5 5 4.5s5-1.5 5-4.5V4",
};

export function DominionGlyph({
  dominion,
  size = 22,
  className,
}: {
  dominion: Dominion;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="square"
      aria-hidden
      className={cn("shrink-0", className)}
    >
      <path d={PATHS[dominion]} />
    </svg>
  );
}
