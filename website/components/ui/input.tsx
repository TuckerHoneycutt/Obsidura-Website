"use client";

import {
  useState,
  type InputHTMLAttributes,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
  type TextareaHTMLAttributes,
} from "react";
import { motion, useMotionTemplate, useMotionValue } from "motion/react";
import { cn } from "@/lib/utils";

const RADIUS = 100;

/**
 * Aceternity UI "Input": the field's edge lights up in a soft ring that
 * follows the pointer while it is over the field.
 *
 * Adapted: the blue ring is --accent-deep, corners are square, and the
 * field keeps the site's own type and border (passed in by the caller).
 * The same frame also wraps a textarea, which the kit does not ship.
 */
function GlowFrame({ children }: { children: ReactNode }) {
  const [visible, setVisible] = useState(false);
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const background = useMotionTemplate`radial-gradient(${visible ? RADIUS + "px" : "0px"} circle at ${mouseX}px ${mouseY}px, var(--accent-deep), transparent 80%)`;

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
    <motion.div
      style={{ background }}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      className="group/input p-px transition duration-300"
    >
      {children}
    </motion.div>
  );
}

export function Input({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <GlowFrame>
      <input className={cn("block", className)} {...props} />
    </GlowFrame>
  );
}

export function Textarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <GlowFrame>
      <textarea className={cn("block", className)} {...props} />
    </GlowFrame>
  );
}
