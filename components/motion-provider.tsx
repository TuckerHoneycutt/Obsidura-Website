"use client";

import { MotionConfig } from "motion/react";

/** Honors the user's prefers-reduced-motion setting for all motion animations. */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
