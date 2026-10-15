"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Aceternity UI "Stateful Button": a spinner slides in beside the label
 * while the action runs.
 *
 * Adapted: the stock button owns its own onClick and plays loading then
 * success around it, which does not fit a submit button whose outcome
 * replaces the whole form. This one is driven by a `pending` prop instead,
 * and wears the site's inverted kicker dress in place of a green pill.
 */
export function StatefulButton({
  pending = false,
  disabled,
  className,
  children,
  // These collide with motion's own handler types, as in the original.
  /* eslint-disable @typescript-eslint/no-unused-vars */
  onDrag,
  onDragStart,
  onDragEnd,
  onAnimationStart,
  onAnimationEnd,
  /* eslint-enable @typescript-eslint/no-unused-vars */
  ...props
}: {
  pending?: boolean;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <motion.button
      layout
      {...props}
      aria-busy={pending || undefined}
      disabled={pending || disabled}
      className={cn(
        "flex min-w-[120px] items-center justify-center gap-2",
        className
      )}
    >
      <AnimatePresence initial={false}>
        {pending && (
          <motion.svg
            key="loader"
            aria-hidden
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 16, opacity: 1, rotate: 360 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{
              width: { duration: 0.2 },
              opacity: { duration: 0.2 },
              rotate: { duration: 0.6, repeat: Infinity, ease: "linear" },
            }}
            viewBox="0 0 24 24"
            height={16}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="square"
          >
            <path d="M12 3a9 9 0 1 0 9 9" />
          </motion.svg>
        )}
      </AnimatePresence>
      <motion.span layout>{children}</motion.span>
    </motion.button>
  );
}
