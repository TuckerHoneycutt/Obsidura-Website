import { ChipRow } from "@/components/ui/chip-row";
import { FramePanel } from "@/components/ui/frame-panel";
import { GlowPanel } from "@/components/ui/glow-panel";
import { Magnetic } from "@/components/ui/magnetic";
import { Reveal } from "@/components/ui/reveal";
import { RuneDivider, RuneMark } from "@/components/ui/rune-mark";
import { LogoMark } from "@/components/logo-mark";

const OPTIONS = [
  {
    name: "Obsidura Cloud",
    realm: "asgard",
    detail: "Fully managed - live in days",
    meta: "multi-tenant / us + eu regions",
  },
  {
    name: "Private VPC",
    realm: "midgard",
    detail: "Runs inside your AWS or GCP account",
    meta: "single-tenant / your network boundary",
  },
  {
    name: "On-Prem",
    realm: "niflheim",
    detail: "Air-gapped - your hardware",
    meta: "kubernetes / no external calls",
  },
];

export function Deploy() {
  return (
    <section id="deploy" className="relative border-t border-rule">
      <RuneDivider />
      <div className="mx-auto max-w-6xl px-5 py-20 lg:py-28">
        <Reveal>
          <p className="kicker text-accent">04 &mdash; the realms</p>
          <h2 className="font-display mt-6 max-w-2xl text-[clamp(2.25rem,4.5vw,3.5rem)] leading-[1.06] font-light tracking-tight">
            Your data stays{" "}
            <span className="headline-emph">where you put it.</span>
          </h2>
        </Reveal>

        <div className="mt-12 grid gap-6 sm:grid-cols-3">
          {OPTIONS.map((opt, i) => (
            <Reveal key={opt.name} delay={i * 0.1} className="h-full">
              <GlowPanel className="bg-paper-warm/30 transition-colors hover:bg-paper-warm/70">
                <div className="relative flex h-full flex-col px-5 py-6">
                  <span className="kicker text-accent">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="mt-4 font-display text-2xl font-medium tracking-tight">
                    {opt.name}
                  </h3>
                  <p className="mt-2 font-mono text-[13px] leading-relaxed text-ink-soft">
                    {opt.detail}
                  </p>
                  <ChipRow
                    items={[
                      <span
                        key="realm"
                        className="flex items-center gap-1.5 text-accent"
                      >
                        <RuneMark size={9} />
                        {opt.realm}
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
            <div className="relative overflow-hidden">
              <div
                aria-hidden
                className="pointer-events-none absolute -top-24 -right-20 opacity-[0.07]"
              >
                <LogoMark size={340} spin="slow" />
              </div>
              <div className="relative flex flex-col items-start gap-6 px-6 py-8 sm:flex-row sm:items-center sm:justify-between">
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
                    href="mailto:hello@obsidura.com"
                    className="kicker inline-block bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
                  >
                    Book a demo
                  </a>
                </Magnetic>
              </div>
            </div>
          </FramePanel>
        </Reveal>
      </div>
    </section>
  );
}
