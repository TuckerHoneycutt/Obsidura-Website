import { Cued } from "@/components/sketches/cued";
import { SketchLead, SketchTag } from "@/components/sketches/lead";

export const metadata = { title: "Sketch C: Points that cue the film - Obsidura" };

export default function SketchCued() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <SketchLead next="#cued" />
      <section id="cued" className="px-5 pb-24 md:pb-32">
        <Cued />
      </section>
      <SketchTag name="C" />
    </main>
  );
}
