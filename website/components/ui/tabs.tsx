"use client";

import type { ComponentProps } from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

/**
 * Site-styled Radix tabs. The list is a rule with the active tab's ink
 * sitting on it; no pill, no fill — the same hairline language as every
 * other seam on the site.
 */
export const Tabs = TabsPrimitive.Root;

export function TabsList({
  className,
  ...props
}: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn("flex border-b border-rule", className)}
      {...props}
    />
  );
}

export function TabsTrigger({
  className,
  ...props
}: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "kicker relative px-4 py-3 !text-[10px] text-ink-mute transition-colors hover:text-ink data-[state=active]:text-accent",
        "after:absolute after:inset-x-0 after:-bottom-px after:h-px after:bg-transparent data-[state=active]:after:bg-accent",
        className
      )}
      {...props}
    />
  );
}

export function TabsContent({
  className,
  ...props
}: ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={className} {...props} />;
}
