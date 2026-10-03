"use client";

import Image from "next/image";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * The Obsidura pinwheel mark, inverted to cream for the dark paper.
 * spin="slow" gives a continuous rotation suited to the four-armed shape.
 * The raster mark is cropped a few percent taller than square, so it sits
 * object-contain inside the square box rather than stretched to fill it.
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
        src="/obsidura-mark.png"
        alt=""
        width={800}
        height={823}
        className="logo-invert size-full object-contain select-none"
        loading={size > 40 ? "eager" : "lazy"}
      />
    </motion.span>
  );
}
