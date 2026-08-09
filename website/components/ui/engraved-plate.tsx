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
    <FramePanel
      interactive={false}
      className={cn("inline-block bg-paper-warm/30", className)}
    >
      {/*
        Centre the engraving as one block. text-align:center would centre
        each line and shear the drawing; flex centres the pre's content box.
      */}
      <div className="flex items-center justify-center overflow-hidden px-3 py-4">
        <pre
          aria-hidden
          className={cn(
            // Full ink on framed plates: readable as engravings without
            // competing with nearby headlines (those sit outside the frame).
            "m-0 font-mono whitespace-pre select-none text-[5px] leading-[5.5px] text-ink",
            preClassName
          )}
        >
          {art}
        </pre>
      </div>
    </FramePanel>
  );
}
