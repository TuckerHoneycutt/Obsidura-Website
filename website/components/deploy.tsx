import Link from "next/link";
import { ChipRow } from "@/components/ui/chip-row";
import { Engraving } from "@/components/ui/engraving";
import { FramePanel } from "@/components/ui/frame-panel";
import { Magnetic } from "@/components/ui/magnetic";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider, MeanderMark } from "@/components/ui/meander-mark";
import { romanNumeral } from "@/lib/utils";
import type { EngravingName } from "@/lib/engravings";

// After the war, the three brothers drew lots for the cosmos: Zeus took
// the heavens, Poseidon the sea, Hades the unseen world below.
const OPTIONS: {
  name: string;
  dominion: string;
  detail: string;
  body: string;
  meta: string;
  href: string;
  art: EngravingName;
}[] = [
  {
    name: "Obsidura Cloud",
    dominion: "zeus",
    detail: "Fully managed in the heavens - live in days",
    body: "We operate the control plane, the executor, and the worker pool. You author definitions and watch runs; none of the infrastructure is yours to carry.",
    meta: "managed / we operate the control plane",
    href: "/deployment/cloud",
    art: "zeus",
  },
  {
    name: "Private VPC",
    dominion: "poseidon",
    detail: "Runs in your own waters - your AWS or GCP account",
    body: "A single-tenant deployment inside your own network boundary. Your data never leaves the account it already lives in, and the proxy holds credentials you issued.",
    meta: "single-tenant / your network boundary",
    href: "/deployment/private-vpc",
    art: "poseidon",
  },
  {
    name: "On-Prem",
    dominion: "hades",
    detail: "Isolated and unseen - your hardware",
    body: "Containers on hardware you own, making no outbound calls at all. For the rooms where the network diagram is the compliance argument.",
    meta: "containers / no outbound calls",
    href: "/deployment/on-premises",
    art: "hades",
  },
];

/**
 * The body of the dominions chapter. Each option gets its engraving at full
 * size rather than a thumbnail - these are 110-line drawings, and needing the
 * room is much of why the chapters have pages of their own now.
 */
export function DeployBody() {
  return (
    <>
      {OPTIONS.map((opt, i) => (
        <section
          key={opt.name}
          className="relative border-t border-rule odd:bg-paper-warm/40"
        >
          <MeanderDivider />
          <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
            <div className="grid items-center gap-10 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
              <Reveal className={i % 2 === 1 ? "lg:order-2" : undefined}>
                <Engraving name={opt.art} maxHeight={620} dim />
              </Reveal>

              <Reveal
                delay={0.1}
                className={i % 2 === 1 ? "lg:order-1" : undefined}
              >
                <span className="kicker text-accent">
                  {romanNumeral(i + 1)}
                </span>
                <h2 className="font-display mt-3 text-[clamp(1.9rem,3.4vw,2.75rem)] leading-tight font-light tracking-tight">
                  {opt.name}
                </h2>
                <p className="lede-copy mt-4">{opt.detail}</p>
                <p className="body-copy mt-4 max-w-lg">{opt.body}</p>
                <Link
                  href={opt.href}
                  className="kicker link-sweep mt-5 inline-block text-accent transition-colors hover:text-ink"
                >
                  the full account &rarr;
                </Link>
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
                  className="mt-7"
                />
              </Reveal>
            </div>
          </div>
        </section>
      ))}

      <section className="relative border-t border-rule">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <Reveal>
            <FramePanel className="bg-paper-warm/40">
              <div className="flex flex-col items-start gap-6 px-6 py-8 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="font-display text-3xl font-light tracking-tight">
                    Put agents on your backend.
                  </h2>
                  <p className="body-copy mt-2 max-w-md text-ink-mute">
                    A 30-minute call. We map one workflow and show you the
                    audit log by the end of it.
                  </p>
                </div>
                <Magnetic className="shrink-0">
                  <Link
                    href="/contact"
                    className="kicker inline-block bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
                  >
                    Book a demo
                  </Link>
                </Magnetic>
              </div>
            </FramePanel>
          </Reveal>
        </div>
      </section>
    </>
  );
}
