import { ChipRow } from "@/components/ui/chip-row";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderDivider, MeanderMark } from "@/components/ui/meander-mark";
import { Reveal } from "@/components/ui/reveal";
import { FACES, WORK } from "@/lib/work";

// Two lists rather than one, because half of what a stranger needs to know
// about this category is what it is *not* - the word "agent" arrives with a
// chatbot attached to it, and that has to be set down before anything else
// lands.
const DOES = [
  "Reaches the places your information already lives — databases, file storage, internal sites, cloud tools — and works across all of them in one job.",
  "Starts on a schedule, on a call from another system, or when a person presses a button or asks in plain words.",
  "Uses an AI agent where judgement is needed and an ordinary script where it is not — in the same process.",
  "Hands each step only the data the person who asked is cleared to see.",
  "Checks every result against the shape it was promised, and keeps a record of every call, decision, and retry.",
  "Keeps the processes themselves under management: versioned, watched, and held for sign-off where you say so.",
];

const DOES_NOT = [
  "A chatbot, or an assistant in your editor. Most of what it does, nobody watches.",
  "A tool for one kind of task. Reports are the easiest thing to show on a page, not the boundary.",
  "A model of ours. Bring the one you prefer — it runs as one step inside the job.",
  "A place your data moves to. Run it in our cloud, in your own account, or fully offline.",
];

function List({ label, items }: { label: string; items: string[] }) {
  return (
    <FramePanel className="h-full bg-paper-warm/30">
      <p className="kicker border-b border-rule px-5 py-2.5 !text-[10px] text-accent">
        {label}
      </p>
      <ul className="space-y-4 px-5 py-5">
        {items.map((item) => (
          <li key={item} className="flex gap-3">
            <MeanderMark size={10} className="mt-2 text-ink-faint" />
            <span className="body-copy-sm">{item}</span>
          </li>
        ))}
      </ul>
    </FramePanel>
  );
}

function Face({ face }: { face: (typeof FACES)[number] }) {
  return (
    <FramePanel className="h-full bg-paper-warm/30">
      <div className="flex h-full flex-col">
        <p className="kicker border-b border-rule px-5 py-2.5 !text-[10px] text-accent">
          {face.label}
        </p>
        <div className="px-5 py-5">
          <h3 className="font-display text-[clamp(1.5rem,2.6vw,2rem)] leading-tight font-light tracking-tight">
            {face.title}
          </h3>
          <p className="body-copy mt-3.5">{face.plain}</p>
        </div>
        <div className="mt-auto space-y-2 border-t border-rule px-5 py-4">
          {face.lines.map((line) => (
            <p
              key={line}
              className="font-mono text-[11px] leading-relaxed break-words text-ink-mute"
            >
              {line}
            </p>
          ))}
        </div>
      </div>
    </FramePanel>
  );
}

/**
 * The body of the works chapter: what Pantheon actually runs. The four kinds
 * of work first, because "a cron job", "an action", "a workflow", and "a chat
 * that knows your data" read as different products to most readers and it
 * matters that they run against one layer here. Then the range, stated as
 * eight ordinary jobs rather than as a claim about generality.
 */
export function AutomationsBody() {
  return (
    <>
      <section className="relative border-t border-rule">
        <MeanderDivider />
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <Reveal className="max-w-3xl">
            <p className="kicker text-accent">four kinds, one layer</p>
            <h2 className="font-display mt-6 text-[clamp(1.9rem,3.6vw,2.85rem)] leading-[1.08] font-light tracking-tight">
              Cron jobs, actions, workflows,{" "}
              <span className="headline-emph">and plain-English questions.</span>
            </h2>
          </Reveal>

          <div className="mt-10 grid gap-6 lg:grid-cols-2">
            {FACES.map((face, i) => (
              <Reveal key={face.label} delay={0.06 + i * 0.08}>
                <Face face={face} />
              </Reveal>
            ))}
          </div>

          <Reveal delay={0.16}>
            <p className="body-copy mt-8 max-w-3xl text-ink-mute">
              Four kinds of work, one governed layer beneath them. The
              permissions, the checks, and the record do not change with the
              kind of work or the door it came in through.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="relative border-t border-rule">
        <MeanderDivider />
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <div className="grid gap-6 lg:grid-cols-2">
            <Reveal>
              <List label="what it does" items={DOES} />
            </Reveal>
            <Reveal delay={0.08}>
              <List label="what it is not" items={DOES_NOT} />
            </Reveal>
          </div>
        </div>
      </section>

      <section className="relative border-t border-rule bg-paper-warm/40">
        <MeanderDivider />
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <Reveal className="max-w-3xl">
            <p className="kicker text-accent">the range</p>
            <h2 className="font-display mt-6 text-[clamp(1.9rem,3.6vw,2.85rem)] leading-[1.08] font-light tracking-tight">
              What it <span className="headline-emph">can automate.</span>
            </h2>
            <p className="lede-copy mt-6">
              Eight ordinary jobs from eight parts of a company &mdash; to the
              engine, all the same shape: a task, a permission, a check, a
              record.
            </p>
            <p className="body-copy mt-5">
              Most of them were automatable all along; they were not{" "}
              <em>worth</em> automating, because wiring one job safely across
              four systems cost more than doing it by hand. Pantheon pays for
              the wiring once, in the engine, and every job after the first
              inherits it.
            </p>
          </Reveal>

          <ul className="mt-10 grid gap-x-10 gap-y-px sm:grid-cols-2">
            {WORK.map((item, i) => (
              <Reveal key={item.domain} delay={Math.min(i * 0.04, 0.24)}>
                <li className="flex flex-col gap-1.5 border-t border-rule py-5 sm:flex-row sm:gap-6">
                  <span className="kicker shrink-0 !text-[10px] text-accent sm:w-28">
                    {item.domain}
                  </span>
                  <span className="body-copy-sm">{item.line}</span>
                </li>
              </Reveal>
            ))}
          </ul>

          <Reveal delay={0.2}>
            <div className="mt-10 border-t border-rule pt-8">
              <p className="body-copy max-w-3xl">
                The engine cannot tell a rocket from a light switch. The work
                your company does is written down as definitions, not built
                into the machinery &mdash; which is what makes the range
                honest rather than a boast.
              </p>
              <ChipRow
                className="mt-6"
                items={[
                  "agents where judgement is needed",
                  "plain scripts where it is not",
                  "a person in the loop where you say so",
                ]}
              />
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
