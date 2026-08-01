"use client";

import { useRef } from "react";
import { FramePanel } from "@/components/ui/frame-panel";
import { cn } from "@/lib/utils";

/**
 * FramePanel with a soft accent glow that follows the pointer
 * (Aceternity hover-card pattern).
 */
export function GlowPanel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={ref}
      className="group/glow h-full"
      onMouseMove={(e) => {
        const rect = ref.current?.getBoundingClientRect();
        if (!rect) return;
        ref.current?.style.setProperty("--gx", `${e.clientX - rect.left}px`);
        ref.current?.style.setProperty("--gy", `${e.clientY - rect.top}px`);
      }}
    >
      <FramePanel className={cn("h-full", className)}>
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover/glow:opacity-100"
          style={{
            background:
              "radial-gradient(220px circle at var(--gx, 50%) var(--gy, 50%), var(--gilt-glow), transparent 70%)",
          }}
        />
        {children}
      </FramePanel>
    </div>
  );
}
