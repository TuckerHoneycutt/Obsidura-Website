import { Hero } from "@/components/hero";
import { Integrations } from "@/components/integrations";
import { ChapterIndex } from "@/components/chapter-index";
import { Reveal } from "@/components/ui/reveal";
import { MeanderMark } from "@/components/ui/meander-mark";

/**
 * The homepage is a door, not a summary. One claim at full force, the mark,
 * two ways in, and the index of the five chapters. Everything that used to
 * scroll past here now has a page of its own, which is what gives the
 * engravings room to be seen at the size they were drawn.
 */
export default function Home() {
  return (
    <main className="flex-1">
      <Hero />
      <Integrations />
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
