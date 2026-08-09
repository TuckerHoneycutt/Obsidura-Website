import { cn } from "@/lib/utils";

function Seal({
  className,
  interactive,
}: {
  className?: string;
  interactive: boolean;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "pointer-events-none absolute size-[7px] border border-rule bg-paper",
        interactive &&
          "transition-colors duration-300 group-hover/frame:border-accent-deep",
        className
      )}
    />
  );
}

/**
 * Editorial framed panel: hairline border with small square seals at each
 * corner, echoing print registration marks.
 *
 * `interactive={false}` freezes the frame - used by plates that should read as
 * printed matter rather than as something you can point at.
 */
export function FramePanel({
  className,
  children,
  interactive = true,
}: {
  className?: string;
  children: React.ReactNode;
  interactive?: boolean;
}) {
  return (
    <div
      className={cn(
        "relative border border-rule",
        interactive &&
          "group/frame transition-colors duration-300 hover:border-rule/80",
        className
      )}
    >
      <Seal interactive={interactive} className="-top-1 -left-1" />
      <Seal interactive={interactive} className="-top-1 -right-1" />
      <Seal interactive={interactive} className="-bottom-1 -left-1" />
      <Seal interactive={interactive} className="-bottom-1 -right-1" />
      {children}
    </div>
  );
}
