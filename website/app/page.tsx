import { Hero } from "@/components/hero";
import { Integrations } from "@/components/integrations";
import { WhatItRuns } from "@/components/what-it-runs";
import { ChapterIndex } from "@/components/chapter-index";
import { Reveal } from "@/components/ui/reveal";
import { MeanderMark } from "@/components/ui/meander-mark";

/**
 * A door, and only a door. It has two jobs: say what Pantheon is in the few
 * seconds a stranger gives it, and say that the range is wider than whatever
 * example they picture first. Everything else - the definition at length, the
 * run walked through step by step, what happens when a run fails, the
 * evidence for any of it - has a chapter of its own, and the index below is
 * how you get there.
 */
export default function Home() {
  return (
    <main className="flex-1">
      <Hero />
      <Integrations />
      <WhatItRuns />
      <ChapterIndex />

      <section className="relative border-t border-rule">
        <Reveal className="mx-auto max-w-4xl px-5 py-20 text-center lg:py-28">
          <MeanderMark size={12} className="mx-auto text-ink-faint" />
          <p className="font-display mt-6 text-[clamp(1.6rem,3vw,2.5rem)] leading-snug font-light text-ink">
            Where toil belongs to the agents,
            <br />
            <span className="italic text-ink-soft">
              judgement ascends to Olympus.
            </span>
          </p>
        </Reveal>
      </section>
    </main>
  );
}
