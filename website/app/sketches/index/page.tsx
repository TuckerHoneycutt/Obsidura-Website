import { ChapterIndex } from "@/components/sketches/chapters";
import { FilmPlate, FilmProvider } from "@/components/sketches/film";
import { SketchLead, SketchTag } from "@/components/sketches/lead";
import { Points } from "@/components/sketches/points";

export const metadata = { title: "Sketch A: Plate and contents - Obsidura" };

/**
 * Sketch A - plate and contents. The points get a screen to themselves,
 * then the film is set beside its own contents page: eight chapters, by the
 * film's own labels, that show where you are and take you anywhere in it.
 * Four minutes becomes something you can skim.
 */
export default function SketchIndex() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <SketchLead next="#points" />

      <section id="points" className="flex justify-center px-5 py-24 md:py-32">
        <Points />
      </section>

      <section className="px-5 pb-24 md:pb-32">
        <FilmProvider>
          <div className="mx-auto grid max-w-6xl items-start gap-8 lg:grid-cols-[minmax(0,1fr)_15rem] lg:gap-12">
            <FilmPlate />
            <ChapterIndex className="lg:pt-3" />
          </div>
        </FilmProvider>
      </section>

      <SketchTag name="A" />
    </main>
  );
}
