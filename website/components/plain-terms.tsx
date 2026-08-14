import { MeanderDivider } from "@/components/ui/meander-mark";
import { Reveal } from "@/components/ui/reveal";

/**
 * The definition, and nothing else. A reader who stops here should be able to
 * say what the product is out loud to somebody else - which takes a paragraph.
 * It opens the works chapter rather than the homepage: a stranger on the front
 * page gets the one-sentence version in the hero and a way through to this.
 */
export function PlainTerms() {
  return (
    <section className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <Reveal className="max-w-3xl">
          <p className="kicker text-accent">in plain terms</p>
          <h2 className="font-display mt-6 text-[clamp(2rem,4vw,3.15rem)] leading-[1.06] font-light tracking-tight">
            Define it once, run it forever,{" "}
            <span className="headline-emph">and keep it under management.</span>
          </h2>
          <p className="lede-copy mt-7">
            Pantheon is a workflow automation platform: a place to define, run,
            and manage reliable processes, built from ordinary scripted tasks
            and AI agents in the same job. A process is written down once and
            then runs, over and over, without anyone minding it. An agent may
            do the thinking, but the engine decides what it can reach, checks
            what it produces, and keeps the record of what happened.
          </p>
        </Reveal>

        <Reveal delay={0.1}>
          <p className="font-display mx-auto mt-11 max-w-3xl text-center text-[clamp(1.2rem,2vw,1.6rem)] leading-snug font-light text-ink-soft">
            The agent is the clerk.{" "}
            <span className="italic text-ink">
              Pantheon is the building: the vault, the rule about which drawer
              that clerk may open, the ledger of the ones they did, and the
              night shift that runs when the clerk has gone home.
            </span>
          </p>
        </Reveal>
      </div>
    </section>
  );
}
