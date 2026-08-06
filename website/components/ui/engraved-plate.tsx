import { FramePanel } from "@/components/ui/frame-panel";
import { cn } from "@/lib/utils";

/**
 * A static high-density ASCII engraving in a sealed frame. Matches the
 * Mount Olympus / Herakles treatment: fine glyphs, no caption, no reveal.
 */
export function EngravedPlate({
  art,
  className,
  preClassName,
}: {
  art: string;
  className?: string;
  preClassName?: string;
}) {
  return (
    <FramePanel className={cn("inline-block bg-paper-warm/30", className)}>
      <pre
        aria-hidden
        className={cn(
          // Full ink on framed plates: readable as engravings without
          // competing with nearby headlines (those sit outside the frame).
          "px-3 py-4 font-mono select-none text-[5px] leading-[5.5px] text-ink",
          preClassName
        )}
      >
        {art}
      </pre>
    </FramePanel>
  );
}
