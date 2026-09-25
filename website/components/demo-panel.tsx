import Link from "next/link";
import { FramePanel } from "@/components/ui/frame-panel";
import { Magnetic } from "@/components/ui/magnetic";
import { cn } from "@/lib/utils";

/**
 * The closing offer every chapter and landing page ends on. One component, so
 * the promise - one job, thirty minutes, an audit log by the end - reads the
 * same wherever a reader finishes.
 */
export function DemoPanel({ className }: { className?: string }) {
  return (
    <FramePanel className={cn("bg-paper-warm/40", className)}>
      <div className="flex flex-col items-start gap-6 px-[clamp(1.5rem,3vw,3rem)] py-[clamp(2rem,3vw,2.75rem)] sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-light tracking-tight">
            Put Pantheon to work.
          </h2>
          <p className="body-copy mt-2 max-w-xl">
            A 30-minute call. We map one job you already do by hand and show
            you the audit log by the end of it.
          </p>
        </div>
        <Magnetic className="shrink-0">
          <Link
            href="/contact"
            className="kicker inline-block bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
          >
            Book a demo
          </Link>
        </Magnetic>
      </div>
    </FramePanel>
  );
}
