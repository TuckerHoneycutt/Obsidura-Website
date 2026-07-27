import { cn } from "@/lib/utils";

/**
 * Joined mono chips: bordered labels that share edges, like a printed
 * specimen sheet. Chips after the first drop their left border so the rules
 * never double up.
 */
export function ChipRow({
  items,
  className,
}: {
  items: React.ReactNode[];
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap", className)}>
      {items.map((item, i) => (
        <span
          key={i}
          className="kicker !text-[10px] flex items-center gap-1.5 border border-rule px-2.5 py-1.5 not-first:border-l-0"
        >
          {item}
        </span>
      ))}
    </div>
  );
}
