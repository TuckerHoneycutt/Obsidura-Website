"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

const open = {
  transition: { delay: 0.3, duration: 0.8, ease: "easeInOut" as const },
  viewport: { once: true },
};

/**
 * Aceternity UI "Lamp": two cones of light open out from a bright filament
 * and wash down over whatever sits beneath.
 *
 * Adapted: the cyan light is gold leaf (--gilt) and every slate-950 mask is
 * --paper, so the lamp burns on obsidian in the dark theme and casts a warm
 * shadow on the light one. The stock version leans on a bg-gradient-conic
 * plugin class and a full-screen height; the cones here are plain inline
 * conic-gradients and the stage is sized to a closing section.
 */
export function LampContainer({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative z-0 flex min-h-[36rem] w-full flex-col items-center justify-center overflow-hidden bg-paper",
        className
      )}
    >
      <div
        aria-hidden
        className="relative isolate z-0 flex w-full flex-1 scale-y-125 items-center justify-center"
      >
        <motion.div
          initial={{ opacity: 0.5, width: "15rem" }}
          whileInView={{ opacity: 1, width: "30rem" }}
          {...open}
          style={{
            backgroundImage:
              "conic-gradient(from 70deg at center top, var(--gilt), transparent, transparent)",
          }}
          className="absolute inset-auto right-1/2 h-56 w-[30rem] overflow-visible"
        >
          <div className="absolute bottom-0 left-0 z-20 h-40 w-full bg-paper [mask-image:linear-gradient(to_top,white,transparent)]" />
          <div className="absolute bottom-0 left-0 z-20 h-full w-40 bg-paper [mask-image:linear-gradient(to_right,white,transparent)]" />
        </motion.div>
        <motion.div
          initial={{ opacity: 0.5, width: "15rem" }}
          whileInView={{ opacity: 1, width: "30rem" }}
          {...open}
          style={{
            backgroundImage:
              "conic-gradient(from 290deg at center top, transparent, transparent, var(--gilt))",
          }}
          className="absolute inset-auto left-1/2 h-56 w-[30rem]"
        >
          <div className="absolute right-0 bottom-0 z-20 h-full w-40 bg-paper [mask-image:linear-gradient(to_left,white,transparent)]" />
          <div className="absolute right-0 bottom-0 z-20 h-40 w-full bg-paper [mask-image:linear-gradient(to_top,white,transparent)]" />
        </motion.div>
        <div className="absolute top-1/2 h-48 w-full translate-y-12 scale-x-150 bg-paper blur-2xl" />
        <div className="absolute top-1/2 z-50 h-48 w-full bg-transparent opacity-10 backdrop-blur-md" />
        <div className="absolute inset-auto z-50 h-36 w-[28rem] -translate-y-1/2 rounded-full bg-[var(--gilt)] opacity-40 blur-3xl" />
        <motion.div
          initial={{ width: "8rem" }}
          whileInView={{ width: "16rem" }}
          {...open}
          className="absolute inset-auto z-30 h-36 w-64 -translate-y-[6rem] rounded-full bg-[var(--gilt)] opacity-70 blur-2xl"
        />
        <motion.div
          initial={{ width: "15rem" }}
          whileInView={{ width: "30rem" }}
          {...open}
          className="absolute inset-auto z-50 h-px w-[30rem] -translate-y-[7rem] bg-[var(--gilt)]"
        />
        <div className="absolute inset-auto z-40 h-44 w-full -translate-y-[12.5rem] bg-paper" />
      </div>

      <div className="relative z-50 flex -translate-y-40 flex-col items-center px-5">
        {children}
      </div>
    </div>
  );
}
