"use client";

import Link from "next/link";
import { HoverBorderGradient } from "@/components/ui/hover-border-gradient";
import { Spotlight } from "@/components/ui/spotlight";

/**
 * The hero's first screen, held still: every sketch opens the same way so
 * only what follows it differs.
 */
export function SketchLead({ next }: { next: string }) {
  return (
    <section className="relative overflow-clip">
      <Spotlight />
      <div className="mx-auto flex min-h-[calc(100svh-4rem)] max-w-6xl flex-col items-center justify-center px-5 text-center md:min-h-[calc(100svh-4.8125rem)]">
        <h1 className="font-display text-[clamp(2.4rem,5.4vw,5.25rem)] leading-[1.02] font-light tracking-tight">
          The Unified Infrastructure for Software
        </h1>
        <div className="mt-12">
          <HoverBorderGradient
            as={Link}
            href="/contact"
            duration={1.2}
            className="kicker px-6 py-3.5 !text-ink"
          >
            Book a demo
          </HoverBorderGradient>
        </div>
        <a
          href={next}
          className="kicker mt-14 flex flex-col items-center gap-3 text-ink-mute transition-colors hover:text-ink"
        >
          Scroll to discover
          <span aria-hidden className="animate-scroll-cue block h-8 w-px bg-current" />
        </a>
      </div>
    </section>
  );
}

/** Marks a sketch page as a sketch, so nobody mistakes it for the site. */
export function SketchTag({ name }: { name: string }) {
  return (
    <p className="kicker fixed right-6 bottom-6 z-[90] border border-rule bg-paper px-2.5 py-1.5 whitespace-nowrap !text-[0.625rem] !tracking-[0.16em] text-ink-faint md:right-8 md:bottom-8">
      Sketch {name}
    </p>
  );
}
