import { Hero } from "@/components/hero";
import { WhatItRuns } from "@/components/what-it-runs";

/**
 * A door, and only a door: say what Obsidura is in the few seconds a
 * stranger gives it, and say that the range is wider than whatever example
 * they picture first. The engine's chapters have retired from the public
 * site; anyone who wants the depth asks for it through Contact.
 */
export default function Home() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <Hero />
      <WhatItRuns />
    </main>
  );
}
