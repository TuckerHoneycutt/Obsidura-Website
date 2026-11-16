import { FilmPlate, FilmProvider } from "@/components/sketches/film";
import { SketchLead, SketchTag } from "@/components/sketches/lead";
import { NUMERALS, POINTS } from "@/lib/home-content";

export const metadata = { title: "Sketch B: Captioned plate - Obsidura" };

/**
 * Sketch B - the captioned plate. One screen after the claim: the film,
 * and under it the three points set as its caption, the way a plate in a
 * book carries its legend. No pinning, no handoffs - the quietest option.
 */
export default function SketchCaption() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <SketchLead next="#film" />

      <section id="film" className="px-5 py-16 md:py-24">
        <figure className="mx-auto max-w-6xl">
          <FilmProvider>
            <FilmPlate />
          </FilmProvider>
          <figcaption className="mt-10 grid gap-8 border-t border-rule pt-8 md:mt-12 md:grid-cols-3 md:gap-10">
            {POINTS.map((text, i) => (
              <div key={text}>
                <p aria-hidden className="kicker mb-3">
                  {NUMERALS[i]}.
                </p>
                <p className="body-copy">{text}</p>
              </div>
            ))}
          </figcaption>
        </figure>
      </section>

      <SketchTag name="B" />
    </main>
  );
}
