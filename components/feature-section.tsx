"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { FramePanel } from "@/components/ui/frame-panel";
import { Parallax } from "@/components/ui/parallax";
import { Reveal } from "@/components/ui/reveal";
import { cn } from "@/lib/utils";

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
  figure: string;
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
    <section id={content.id} className="border-t border-rule">
      <div
        className={cn(
          "mx-auto grid max-w-6xl gap-10 px-5 py-20 lg:grid-cols-2 lg:gap-16 lg:py-28"
        )}
      >
        <Reveal className={cn(content.reverse && "lg:order-2")}>
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

          <h2 className="mt-6 text-4xl leading-[1.08] font-light tracking-tight sm:text-5xl">
            {content.headlineLead}{" "}
            <span className="headline-emph">{content.headlineEmph}</span>
          </h2>

          <p className="mt-6 max-w-lg text-lg leading-relaxed text-ink-soft">
            {content.lede}
          </p>

          <NerdPanel
            open={nerd}
            lede={content.nerdLede}
            bullets={content.nerdBullets}
          />
        </Reveal>

        <Reveal delay={0.15} className={cn(content.reverse && "lg:order-1")}>
          <Parallax offset={36}>
            <FramePanel className="bg-paper-warm/30">
            <div className="flex items-center justify-between border-b border-rule px-5 py-2.5">
              <span className="kicker">{content.id}</span>
              <span className="kicker">{content.figure}</span>
            </div>
            <ul className="divide-y divide-rule">
              {content.bullets.map((b, i) => (
                <li key={b} className="flex gap-4 px-5 py-5">
                  <span className="kicker mt-1 shrink-0 text-accent">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <p className="text-base leading-relaxed text-ink-soft">
                    {b}
                  </p>
                </li>
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
