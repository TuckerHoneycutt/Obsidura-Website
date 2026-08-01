import { ChipRow } from "@/components/ui/chip-row";
import { DominionGlyph } from "@/components/ui/dominion-glyph";
import { FramePanel } from "@/components/ui/frame-panel";
import { GlowPanel } from "@/components/ui/glow-panel";
import { Magnetic } from "@/components/ui/magnetic";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider, MeanderMark } from "@/components/ui/meander-mark";
import { romanNumeral } from "@/lib/utils";

// After the war, the three brothers drew lots for the cosmos: Zeus took
// the heavens, Poseidon the sea, Hades the unseen world below.
const OPTIONS = [
  {
    name: "Obsidura Cloud",
    dominion: "zeus",
    detail: "Fully managed in the heavens - live in days",
    meta: "multi-tenant / us + eu regions",
  },
  {
    name: "Private VPC",
    dominion: "poseidon",
    detail: "Runs in your own waters - your AWS or GCP account",
    meta: "single-tenant / your network boundary",
    href: "/deployment/private-vpc",
  },
  {
    name: "On-Prem",
    dominion: "hades",
    detail: "Air-gapped and unseen - your hardware",
    meta: "kubernetes / no external calls",
    href: "/deployment/on-premises",
  },
] as const;

export function Deploy() {
  return (
    <section id="deploy" className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-20 lg:py-28">
        <Reveal>
          <p className="kicker text-accent">iv &mdash; the dominions</p>
          <h2 className="font-display mt-6 max-w-2xl text-[clamp(2.25rem,4.5vw,3.5rem)] leading-[1.06] font-light tracking-tight">
            Your data stays{" "}
            <span className="headline-emph">in your dominion.</span>
          </h2>
          <p className="mt-5 max-w-xl font-mono text-sm leading-relaxed text-ink-mute">
            When the war was won, the brothers drew lots for the cosmos -
            the heavens, the sea, the world below. Choose your dominion;
            the agents serve in all three.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-6 sm:grid-cols-3">
          {OPTIONS.map((opt, i) => (
            <Reveal key={opt.name} delay={i * 0.1} className="h-full">
              <GlowPanel className="bg-paper-warm/30 transition-colors hover:bg-paper-warm/70">
                <div className="relative flex h-full flex-col px-5 py-6">
                  <div className="flex items-start justify-between">
                    <span className="kicker text-accent">
                      {romanNumeral(i + 1)}
                    </span>
                    <DominionGlyph
                      dominion={opt.dominion}
                      className="text-ink-mute transition-colors duration-300 group-hover/glow:text-[var(--gilt)]"
                    />
                  </div>
                  <h3 className="mt-4 font-display text-2xl font-medium tracking-tight">
                    {opt.name}
                  </h3>
                  <p className="mt-2 font-mono text-[13px] leading-relaxed text-ink-soft">
                    {opt.detail}
                  </p>
                  {"href" in opt && (
                    <a
                      href={opt.href}
                      className="kicker link-sweep mt-3 w-max text-accent transition-colors hover:text-ink"
                    >
                      the full account &rarr;
                    </a>
                  )}
                  <ChipRow
                    items={[
                      <span
                        key="dominion"
                        className="flex items-center gap-1.5 text-accent"
                      >
                        <MeanderMark size={9} />
                        {opt.dominion}
                      </span>,
                      ...opt.meta.split(" / "),
                    ]}
                    className="mt-auto pt-6"
                  />
                </div>
              </GlowPanel>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.2} className="mt-14">
          <FramePanel className="bg-paper-warm/40">
            <div className="flex flex-col items-start gap-6 px-6 py-8 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-display text-3xl font-light tracking-tight">
                  Put agents on your backend.
                </h3>
                <p className="mt-2 max-w-md font-mono text-sm text-ink-mute">
                  A 30-minute call. We map one workflow and show you the
                  audit log by the end of it.
                </p>
              </div>
              <Magnetic className="shrink-0">
                <a
                  href="/contact"
                  className="kicker inline-block bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
                >
                  Book a demo
                </a>
              </Magnetic>
            </div>
          </FramePanel>
        </Reveal>
      </div>
    </section>
  );
}
