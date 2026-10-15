import { Hero } from "@/components/hero";
import {
  ClosingCta,
  Pillars,
  SmallSoftware,
  WhereItRuns,
} from "@/components/home-sections";

/**
 * The claim, then the depth behind it: what small software is, what was
 * hard about it, where it runs, and one way in. Every section restates
 * something the site already says, so the page gains feel, not claims.
 */
export default function Home() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <Hero />
      <SmallSoftware />
      <Pillars />
      <WhereItRuns />
      <ClosingCta />
    </main>
  );
}
