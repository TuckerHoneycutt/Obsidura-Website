import Link from "next/link";
import { ChipRow } from "@/components/ui/chip-row";
import { Engraving } from "@/components/ui/engraving";
import { FramePanel } from "@/components/ui/frame-panel";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider, MeanderMark } from "@/components/ui/meander-mark";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn, romanNumeral } from "@/lib/utils";
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

// The same three options laid over each other, row by row - for the reader
// who has met the dominions above and now wants the differences in one
// glance. Every value restates copy from OPTIONS; nothing new is claimed.
const COMPARE: { name: string; rows: [string, string][] }[] = [
  {
    name: "Obsidura Cloud",
    rows: [
      [
        "the arrangement",
        "Fully managed — we operate the control plane, the executor, and the worker pool.",
      ],
      [
        "where data lives",
        "In our cloud; you author definitions and watch runs.",
      ],
      [
        "the boundary",
        "Ours to carry, with every call passing the run-scoped proxy.",
      ],
    ],
  },
  {
    name: "Private VPC",
    rows: [
      [
        "the arrangement",
        "Single-tenant, deployed inside your own network boundary.",
      ],
      [
        "where data lives",
        "It never leaves the AWS or GCP account it already lives in.",
      ],
      [
        "the boundary",
        "Your account's edge; the proxy holds credentials you issued.",
      ],
    ],
  },
  {
    name: "On-Prem",
    rows: [
      ["the arrangement", "Containers on hardware you own."],
      ["where data lives", "In the room. Nothing about a run leaves it."],
      ["the boundary", "The wall itself — no outbound calls at all."],
    ],
  },
];

/**
 * The body of the dominions chapter. Each option gets its engraving at full
 * size rather than a thumbnail - these are 110-line drawings, and needing the
 * room is much of why the chapters have pages of their own now.
 */
// The tinted band, made opaque so the engraving's own backing can match it
// exactly - a translucent band over the grain has no single colour to match.
const BAND = "bg-[color-mix(in_srgb,var(--paper-warm)_40%,var(--paper))]";

export function DeployBody() {
  return (
    <>
      {OPTIONS.map((opt, i) => (
        <section
          key={opt.name}
          className={cn(
            "relative border-t border-rule",
            i % 2 === 1 && BAND
          )}
        >
          <MeanderDivider />
          <div className="mx-auto max-w-shell px-gutter py-16 lg:py-20">
            <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] lg:gap-16 xl:gap-24">
              <Reveal className={i % 2 === 1 ? "lg:order-2" : undefined}>
                <Engraving
                  name={opt.art}
                  maxHeight={620}
                  dim
                  backing={i % 2 === 1 ? BAND : undefined}
                />
              </Reveal>

              <Reveal
                delay={0.1}
                className={i % 2 === 1 ? "lg:order-1" : undefined}
              >
                <span className="kicker text-accent">
                  {romanNumeral(i + 1)}
                </span>
                <h2 className="font-display mt-3 text-[clamp(1.65rem,3vw,2.4rem)] leading-tight font-light tracking-tight">
                  {opt.name}
                </h2>
                <p className="lede-copy mt-4">{opt.detail}</p>
                <p className="body-copy mt-4 max-w-xl">{opt.body}</p>
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

      <section className="relative border-t border-rule bg-paper-warm/40">
        <MeanderDivider />
        <div className="mx-auto grid max-w-shell items-start gap-10 px-gutter py-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16 lg:py-20 xl:gap-24">
          <Reveal className="max-w-3xl lg:sticky lg:top-24">
            <p className="kicker text-accent">side by side</p>
            <h2 className="font-display mt-6 text-[clamp(1.65rem,3.2vw,2.5rem)] leading-[1.08] font-light tracking-tight">
              The same engine{" "}
              <span className="headline-emph">in all three.</span>
            </h2>
            <p className="body-copy mt-5 text-ink-mute">
              The engine and the security model are identical in all three. What
              changes is who carries the infrastructure, and where the boundary
              sits.
            </p>
          </Reveal>

          <Reveal delay={0.1}>
            <FramePanel className="bg-paper">
              <Tabs defaultValue={COMPARE[0].name}>
                <TabsList>
                  {COMPARE.map((c) => (
                    <TabsTrigger key={c.name} value={c.name}>
                      {c.name}
                    </TabsTrigger>
                  ))}
                </TabsList>
                {COMPARE.map((c, i) => (
                  <TabsContent key={c.name} value={c.name}>
                    <dl className="divide-y divide-rule px-5">
                      {c.rows.map(([term, detail]) => (
                        <div
                          key={term}
                          className="flex flex-col gap-1 py-4 sm:flex-row sm:gap-6 xl:gap-10"
                        >
                          <dt className="kicker shrink-0 !text-[0.71875rem] text-accent sm:w-36">
                            {term}
                          </dt>
                          <dd className="body-copy-sm">{detail}</dd>
                        </div>
                      ))}
                    </dl>
                    <div className="flex items-center justify-between border-t border-rule px-5 py-3.5">
                      <span className="kicker flex items-center gap-1.5 !text-[0.71875rem] text-accent">
                        <MeanderMark size={9} />
                        {OPTIONS[i].dominion}
                      </span>
                      <Link
                        href={OPTIONS[i].href}
                        className="kicker link-sweep !text-[0.71875rem] text-accent transition-colors hover:text-ink"
                      >
                        the full account &rarr;
                      </Link>
                    </div>
                  </TabsContent>
                ))}
              </Tabs>
            </FramePanel>
          </Reveal>
        </div>
      </section>
    </>
  );
}
