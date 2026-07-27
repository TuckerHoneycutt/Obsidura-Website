import { cn } from "@/lib/utils";

function Seal({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "pointer-events-none absolute size-[7px] border border-rule bg-paper transition-colors duration-300 group-hover/frame:border-accent-deep",
        className
      )}
    />
  );
}

/**
 * Editorial framed panel: hairline border with small square seals at each
 * corner, echoing print registration marks.
 */
export function FramePanel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "group/frame relative border border-rule transition-colors duration-300 hover:border-rule/80",
        className
      )}
    >
      <Seal className="-top-1 -left-1" />
      <Seal className="-top-1 -right-1" />
      <Seal className="-bottom-1 -left-1" />
      <Seal className="-bottom-1 -right-1" />
      {children}
    </div>
  );
}
