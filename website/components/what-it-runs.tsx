import Link from "next/link";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { Reveal } from "@/components/ui/reveal";
import { WORK } from "@/lib/work";

// Four of the eight, chosen to be as far apart as the list gets - a report, a
// rocket, a firewall, and a light switch. The homepage only has to break the
// assumption that this makes reports; the chapter carries the rest.
const SHOWN = [WORK[0], WORK[1], WORK[4], WORK[7]];

/**
 * The breadth beat, kept to a strip. A reader who has just been told what
 * Pantheon is will assume it does one kind of thing, and which kind depends on
 * whichever example they saw first - so four examples far apart, the four
 * kinds of work in a sentence, and a way through to the rest.
 */
export function WhatItRuns() {
  return (
    <section className="relative border-t border-rule bg-paper-warm/40">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 pt-10 pb-16 lg:pt-12 lg:pb-20">
        <Reveal className="max-w-3xl">
          <p className="kicker text-accent">what it runs</p>
          <h2 className="font-display mt-6 text-[clamp(1.75rem,3.5vw,2.75rem)] leading-[1.06] font-light tracking-tight">
            Pantheon runs{" "}
            <span className="headline-emph">four kinds of work.</span>
          </h2>
          <p className="lede-copy mt-7">
            Our automation platform, Pantheon, runs cron jobs that recur on
            a schedule, actions fired once, workflows that carry a process
            end to end, and questions asked in chat and answered from the
            context of your data. All four run against the same governed
            layer, and anything software and data can touch is in range.
          </p>
        </Reveal>

        <ul className="mt-10 grid gap-x-12 sm:grid-cols-2">
          {SHOWN.map((item, i) => (
            <Reveal key={item.domain} delay={Math.min(i * 0.05, 0.2)}>
              <li className="flex flex-col gap-1 border-t border-rule py-4 sm:flex-row sm:gap-6">
                <span className="kicker shrink-0 !text-[10px] text-accent sm:w-28">
                  {item.domain}
                </span>
                <span className="body-copy-sm">{item.short}</span>
              </li>
            </Reveal>
          ))}
        </ul>

        <Reveal delay={0.16}>
          <Link
            href="/automations"
            transitionTypes={["nav-forward"]}
            className="kicker link-sweep mt-8 inline-block text-accent transition-colors hover:text-ink"
          >
            the rest of the possibilities, and one job followed to the end &rarr;
          </Link>
        </Reveal>
      </div>
    </section>
  );
}
