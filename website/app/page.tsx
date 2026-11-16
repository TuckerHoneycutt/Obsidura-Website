import { FilmPoints } from "@/components/home/film-points";
import { Lead } from "@/components/home/lead";

/**
 * The claim and one way in, then the plain-language account beside the
 * team film: each point plays the part of the film that shows it. Anyone
 * who wants more depth asks for it through Contact.
 */
export default function Home() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <Lead next="#account" />
      <section id="account" className="scroll-mt-16 px-5 pb-28 md:scroll-mt-20 md:pb-40">
        <FilmPoints />
      </section>
    </main>
  );
}
