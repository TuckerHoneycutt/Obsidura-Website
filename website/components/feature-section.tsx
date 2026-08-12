"use client";

import { motion } from "motion/react";
import { EngravedPlate } from "@/components/ui/engraved-plate";
import { FramePanel } from "@/components/ui/frame-panel";
import { Parallax } from "@/components/ui/parallax";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { cn, romanNumeral } from "@/lib/utils";

export type FeatureContent = {
  id: string;
  kicker: string;
  headlineLead: string;
  headlineEmph: string;
  lede: string;
  bullets: string[];
  nerdLede: string;
  nerdBullets: string[];
  closer?: string;
  reverse?: boolean;
  /** Optional ASCII figure set into the sticky column's dead space. */
  art?: string;
};

export function FeatureSection({ content }: { content: FeatureContent }) {
  return (
    <section id={content.id} className="relative border-t border-rule">
      <MeanderDivider />
      <div
        className={cn(
          "mx-auto grid max-w-6xl gap-10 px-5 py-20 lg:grid-cols-2 lg:gap-16 lg:py-28"
        )}
      >
        <Reveal
          className={cn(
            "lg:sticky lg:top-28 lg:self-start",
            content.reverse && "lg:order-2"
          )}
        >
          <p className="kicker text-accent">{content.kicker}</p>

          <h2 className="font-display mt-6 text-[clamp(2.25rem,4.5vw,3.5rem)] leading-[1.06] font-light tracking-tight">
            {content.headlineLead}{" "}
            <span className="headline-emph">{content.headlineEmph}</span>
          </h2>

          <p className="drop-cap lede-copy mt-6 max-w-lg">{content.lede}</p>

          {/* The technical aside stays in the mono voice - it is the part
              written for someone who wants the mechanism, and the shift in
              face is what marks it as an aside. */}
          <div className="mt-8 border-l-2 border-accent-deep bg-paper-warm/50 px-5 py-5">
            <p className="font-mono text-[13px] leading-relaxed text-ink-soft">
              {content.nerdLede}
            </p>
            <ul className="mt-4 space-y-3">
              {content.nerdBullets.map((b) => (
                <li
                  key={b}
                  className="flex gap-3 font-mono text-[12.5px] leading-relaxed text-ink-mute"
                >
                  <span aria-hidden className="text-accent">
                    &gt;
                  </span>
                  {b}
                </li>
              ))}
            </ul>
          </div>

          {content.art && (
            <div className="mt-12 hidden lg:block">
              <EngravedPlate art={content.art} />
            </div>
          )}
        </Reveal>

        <Reveal delay={0.15} className={cn(content.reverse && "lg:order-1")}>
          <Parallax offset={36}>
            <FramePanel className="bg-paper-warm/30">
              <div className="border-b border-rule px-5 py-2.5">
                <span className="kicker">{content.id}</span>
              </div>
              <ul className="divide-y divide-rule">
                {content.bullets.map((b, i) => (
                  <motion.li
                    key={b}
                    className="flex gap-4 px-5 py-5"
                    initial={{ opacity: 0.35 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ margin: "-15% 0px -15% 0px" }}
                    transition={{ duration: 0.4 }}
                  >
                    <span className="kicker mt-1 w-7 shrink-0 text-accent">
                      {romanNumeral(i + 1)}
                    </span>
                    <p className="body-copy-sm">{b}</p>
                  </motion.li>
                ))}
              </ul>
              {content.closer && (
                <p className="body-copy-sm border-t border-rule px-5 py-4 text-ink-mute">
                  {content.closer}
                </p>
              )}
            </FramePanel>
          </Parallax>
        </Reveal>
      </div>
    </section>
  );
}
