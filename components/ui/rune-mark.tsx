import { cn } from "@/lib/utils";

/**
 * The Algiz rune drawn as SVG strokes - a small tree-like glyph used as the
 * site's recurring Yggdrasil motif. SVG rather than a unicode runic character
 * so it renders identically on every platform.
 */
export function RuneMark({
  size = 12,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 12 16"
      width={size}
      height={(size * 16) / 12}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="square"
      aria-hidden
      className={cn("inline-block shrink-0", className)}
    >
      <path d="M6 15V1M6 6L1 1M6 6l5-5" />
    </svg>
  );
}

/**
 * A rune seal that interrupts a section's top border, like a stamp on the
 * rule line. Parent section must be `relative` with a top border.
 */
export function RuneDivider({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "absolute -top-[10px] left-1/2 -translate-x-1/2 bg-paper px-3 text-ink-faint",
        className
      )}
    >
      <RuneMark size={11} />
    </span>
  );
}
