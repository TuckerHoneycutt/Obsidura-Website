"use client";

import Image from "next/image";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * The Obsidura pinwheel mark, inverted to cream for the dark paper.
 * spin="slow" gives a continuous rotation suited to the four-armed shape.
 * Uses the tightly-cropped vector mark, so `size` is the visible mark size
 * and the square viewBox is centered on the pinwheel's rotation center.
 */
export function LogoMark({
  size = 24,
  spin = "none",
  className,
}: {
  size?: number;
  spin?: "slow" | "drift" | "none";
  className?: string;
}) {
  const spinning = spin !== "none";
  return (
    <motion.span
      className={cn("inline-block shrink-0", className)}
      animate={spinning ? { rotate: 360 } : undefined}
      transition={
        spinning
          ? {
              duration: spin === "slow" ? 48 : 120,
              repeat: Infinity,
              ease: "linear",
            }
          : undefined
      }
      style={{ width: size, height: size }}
    >
      <Image
        src="/logo-mark.svg"
        alt=""
        width={size}
        height={size}
        unoptimized
        className="logo-invert size-full select-none"
        loading={size > 40 ? "eager" : "lazy"}
      />
    </motion.span>
  );
}
