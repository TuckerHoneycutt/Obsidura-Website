import { cn } from "@/lib/utils";

/**
 * A single unit of the Greek key (meander) drawn as SVG strokes - the
 * square spiral used as the site's recurring Pantheon motif. SVG rather
 * than a unicode character so it renders identically on every platform.
 */
export function MeanderMark({
  size = 12,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 12 12"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="square"
      aria-hidden
      className={cn("inline-block shrink-0", className)}
    >
      <path d="M1 11V1h10v7H5V5h3" />
    </svg>
  );
}

/**
 * A running Greek key band: the meander unit repeated edge to edge, the
 * way it appears on temple friezes and pottery rims. A fixed pattern id
 * is safe here because every instance renders the identical tile.
 */
export function MeanderFrieze({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      className={cn("block w-full text-ink-faint", className)}
      height="12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.1"
      strokeLinecap="square"
    >
      <defs>
        <pattern
          id="meander-frieze"
          width="12"
          height="12"
          patternUnits="userSpaceOnUse"
        >
          <path d="M1.5 9.5V2.5h9v5H6V5h2.5" />
        </pattern>
      </defs>
      <rect width="100%" height="12" stroke="none" fill="url(#meander-frieze)" />
    </svg>
  );
}

/**
 * A meander seal that interrupts a section's top border, like a stamp on
 * the rule line. Parent section must be `relative` with a top border.
 */
export function MeanderDivider({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "absolute -top-[7px] left-1/2 -translate-x-1/2 bg-paper px-3 text-ink-faint",
        className
      )}
    >
      <MeanderMark size={11} />
    </span>
  );
}
