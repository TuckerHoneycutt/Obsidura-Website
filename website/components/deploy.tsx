import Link from "next/link";
import { ChipRow } from "@/components/ui/chip-row";
import { Engraving } from "@/components/ui/engraving";
import { FramePanel } from "@/components/ui/frame-panel";
import { Magnetic } from "@/components/ui/magnetic";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider, MeanderMark } from "@/components/ui/meander-mark";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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

// The same three options laid over each other, row by row - for the reader
// who has met the dominions above and now wants the differences in one
// glance. Every value restates copy from OPTIONS; nothing new is claimed.
const COMPARE: { name: string; rows: [string, string][] }[] = [
  {
    name: "Obsidura Cloud",
    rows: [
      ["the arrangement", "Fully managed — we operate the control plane, the executor, and the worker pool."],
      ["where data lives", "In our cloud; you author definitions and watch runs."],
      ["the boundary", "Ours to carry, with every call passing the run-scoped proxy."],
    ],
  },
  {
    name: "Private VPC",
    rows: [
      ["the arrangement", "Single-tenant, deployed inside your own network boundary."],
      ["where data lives", "It never leaves the AWS or GCP account it already lives in."],
      ["the boundary", "Your account's edge; the proxy holds credentials you issued."],
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

      <section className="relative border-t border-rule bg-paper-warm/40">
        <MeanderDivider />
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <Reveal className="max-w-3xl">
            <p className="kicker text-accent">side by side</p>
            <h2 className="font-display mt-6 text-[clamp(1.9rem,3.6vw,2.85rem)] leading-[1.08] font-light tracking-tight">
              The same engine{" "}
              <span className="headline-emph">in all three.</span>
            </h2>
            <p className="body-copy mt-5 text-ink-mute">
              The engine and the security model are identical in all three.
              What changes is who carries the infrastructure, and where the
              boundary sits.
            </p>
          </Reveal>

          <Reveal delay={0.1}>
            <FramePanel className="mt-10 max-w-3xl bg-paper">
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
                          className="flex flex-col gap-1 py-4 sm:flex-row sm:gap-6"
                        >
                          <dt className="kicker shrink-0 !text-[10px] text-accent sm:w-36">
                            {term}
                          </dt>
                          <dd className="body-copy-sm">{detail}</dd>
                        </div>
                      ))}
                    </dl>
                    <div className="flex items-center justify-between border-t border-rule px-5 py-3.5">
                      <span className="kicker flex items-center gap-1.5 !text-[10px] text-accent">
                        <MeanderMark size={9} />
                        {OPTIONS[i].dominion}
                      </span>
                      <Link
                        href={OPTIONS[i].href}
                        className="kicker link-sweep !text-[10px] text-accent transition-colors hover:text-ink"
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

      <section className="relative border-t border-rule">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <Reveal>
            <FramePanel className="bg-paper-warm/40">
              <div className="flex flex-col items-start gap-6 px-6 py-8 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="font-display text-3xl font-light tracking-tight">
                    Put Pantheon to work.
                  </h2>
                  <p className="body-copy mt-2 max-w-md text-ink-mute">
                    A 30-minute call. We map one job you already do by hand
                    and show you the audit log by the end of it.
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
