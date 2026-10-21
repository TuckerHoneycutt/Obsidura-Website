"use client";

import type { HTMLAttributes, MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { motion, useMotionTemplate, useMotionValue } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity UI "Card Spotlight": a pool of light follows the pointer
 * across the card's surface.
 *
 * Adapted: the light is --accent-pale over --paper-warm, so it reads as a
 * lamp passing over paper in either theme. The stock version also mounts a
 * three.js dot-matrix canvas (CanvasRevealEffect) inside the light; that
 * pulls three and @react-three/fiber in for a hover flourish, so this keeps
 * the spotlight and leaves the canvas out.
 */
export function CardSpotlight({
  children,
  radius = 350,
  color = "var(--accent-pale)",
  className,
  ...props
}: {
  radius?: number;
  color?: string;
  children: ReactNode;
} & HTMLAttributes<HTMLDivElement>) {
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const maskImage = useMotionTemplate`radial-gradient(${radius}px circle at ${mouseX}px ${mouseY}px, white, transparent 80%)`;

  function handleMouseMove({
    currentTarget,
    clientX,
    clientY,
  }: ReactMouseEvent<HTMLDivElement>) {
    const { left, top } = currentTarget.getBoundingClientRect();
    mouseX.set(clientX - left);
    mouseY.set(clientY - top);
  }

  return (
    <div
      className={cn(
        "group/spotlight relative border border-rule bg-paper-warm/40 p-10",
        className
      )}
      onMouseMove={handleMouseMove}
      {...props}
    >
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -inset-px z-0 opacity-0 transition duration-300 group-hover/spotlight:opacity-100"
        style={{ backgroundColor: color, maskImage, WebkitMaskImage: maskImage }}
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
