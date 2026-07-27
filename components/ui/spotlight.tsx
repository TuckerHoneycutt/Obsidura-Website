"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity-style ambient spotlight: two soft conic gradients that drift
 * slowly behind the hero content.
 */
export function Spotlight({ className }: { className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 1.6, ease: "easeOut" }}
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-0 overflow-hidden",
        className
      )}
    >
      <motion.div
        animate={{ x: [0, 40, 0], y: [0, -30, 0] }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
        className="absolute -top-48 left-1/4 h-[42rem] w-[42rem] rounded-full opacity-[0.10]"
        style={{
          background:
            "radial-gradient(closest-side, var(--accent), transparent 70%)",
        }}
      />
      <motion.div
        animate={{ x: [0, -50, 0], y: [0, 24, 0] }}
        transition={{ duration: 24, repeat: Infinity, ease: "easeInOut" }}
        className="absolute top-1/3 right-0 h-[36rem] w-[36rem] rounded-full opacity-[0.06]"
        style={{
          background:
            "radial-gradient(closest-side, #8f7bb8, transparent 70%)",
        }}
      />
    </motion.div>
  );
}
