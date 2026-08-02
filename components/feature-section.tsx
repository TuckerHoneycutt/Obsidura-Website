"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AsciiArt } from "@/components/ui/ascii-art";
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
  /** Optional ASCII figure carved into the sticky column's dead space. */
  art?: string;
  artCaption?: string;
};

function NerdPanel({
  open,
  lede,
  bullets,
}: {
  open: boolean;
  lede: string;
  bullets: string[];
}) {
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.4, ease: [0.21, 0.47, 0.32, 0.98] }}
          className="overflow-hidden"
        >
          <div className="mt-6 border-l-2 border-accent-deep bg-paper-warm/50 px-5 py-5">
            <p className="font-mono text-sm leading-relaxed text-ink-soft">
              {lede}
            </p>
            <ul className="mt-4 space-y-3">
              {bullets.map((b) => (
                <li
                  key={b}
                  className="flex gap-3 font-mono text-[13px] leading-relaxed text-ink-mute"
                >
                  <span aria-hidden className="text-accent">
                    &gt;
                  </span>
                  {b}
                </li>
              ))}
            </ul>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function FeatureSection({ content }: { content: FeatureContent }) {
  const [nerd, setNerd] = useState(false);

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
          <div className="flex items-center gap-4">
            <p className="kicker text-accent">{content.kicker}</p>
            <button
              type="button"
              onClick={() => setNerd((v) => !v)}
              aria-expanded={nerd}
              className={cn(
                "kicker border px-2.5 py-1 transition-colors",
                nerd
                  ? "border-accent bg-accent !text-paper"
                  : "border-rule !text-ink-mute hover:border-accent-deep hover:!text-ink"
              )}
            >
              nerd mode {nerd ? "[on]" : "[off]"}
            </button>
          </div>

          <h2 className="font-display mt-6 text-[clamp(2.25rem,4.5vw,3.5rem)] leading-[1.06] font-light tracking-tight">
            {content.headlineLead}{" "}
            <span className="headline-emph">{content.headlineEmph}</span>
          </h2>

          <p className="drop-cap mt-6 max-w-lg font-mono text-sm leading-relaxed text-ink-soft">
            {content.lede}
          </p>

          <NerdPanel
            open={nerd}
            lede={content.nerdLede}
            bullets={content.nerdBullets}
          />

          {content.art && (
            <div className="mt-12 hidden lg:block">
              <AsciiArt
                art={content.art}
                duration={2400}
                className="font-mono text-[10px] leading-[12px] text-ink-mute"
              />
              {content.artCaption && (
                <p className="kicker mt-3 !text-[10px]">
                  {content.artCaption}
                </p>
              )}
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
                  <p className="font-mono text-[13px] leading-relaxed text-ink-soft">
                    {b}
                  </p>
                </motion.li>
              ))}
            </ul>
              {content.closer && (
                <p className="border-t border-rule px-5 py-4 font-mono text-[13px] text-ink-mute">
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
