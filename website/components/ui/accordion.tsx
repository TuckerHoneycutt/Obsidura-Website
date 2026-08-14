"use client";

import type { ComponentProps } from "react";
import * as AccordionPrimitive from "@radix-ui/react-accordion";
import { MeanderMark } from "@/components/ui/meander-mark";
import { cn } from "@/lib/utils";

/**
 * Site-styled Radix accordion. The behavior (keyboard, ARIA, height
 * animation hooks) is Radix's; every visible part is the site's own
 * language - hairline rules, the meander bullet, and a square-linecap
 * plus that turns to a saltire when the entry is open.
 */
export const Accordion = AccordionPrimitive.Root;

export function AccordionItem({
  className,
  ...props
}: ComponentProps<typeof AccordionPrimitive.Item>) {
  return <AccordionPrimitive.Item className={className} {...props} />;
}

function PlusMark() {
  return (
    <svg
      viewBox="0 0 12 12"
      width={12}
      height={12}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="square"
      aria-hidden
      className="mt-3 shrink-0 text-ink-faint transition-transform duration-300 group-hover:text-ink group-data-[state=open]:rotate-45"
    >
      <path d="M6 1v10M1 6h10" />
    </svg>
  );
}

export function AccordionTrigger({
  className,
  children,
  ...props
}: ComponentProps<typeof AccordionPrimitive.Trigger>) {
  return (
    <AccordionPrimitive.Header className="m-0">
      <AccordionPrimitive.Trigger
        className={cn(
          "group flex w-full items-start justify-between gap-6 py-7 text-left",
          className
        )}
        {...props}
      >
        <span className="font-display flex items-start gap-3 text-[1.75rem] leading-snug font-medium tracking-tight">
          <MeanderMark size={10} className="mt-3 shrink-0 text-ink-faint" />
          {children}
        </span>
        <PlusMark />
      </AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  );
}

export function AccordionContent({
  className,
  children,
  ...props
}: ComponentProps<typeof AccordionPrimitive.Content>) {
  return (
    <AccordionPrimitive.Content className="accordion-content" {...props}>
      <div className={cn("body-copy pr-8 pb-8 pl-[22px]", className)}>
        {children}
      </div>
    </AccordionPrimitive.Content>
  );
}
