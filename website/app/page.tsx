import { Hero } from "@/components/hero";
import { Integrations } from "@/components/integrations";
import { WhatItRuns } from "@/components/what-it-runs";
import { ChapterIndex } from "@/components/chapter-index";

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
    </main>
  );
}
