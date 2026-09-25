import Link from "next/link";
import { ChipRow } from "@/components/ui/chip-row";
import { Engraving } from "@/components/ui/engraving";
import { FramePanel } from "@/components/ui/frame-panel";
import { Magnetic } from "@/components/ui/magnetic";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider, MeanderMark } from "@/components/ui/meander-mark";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { CodeRow, Syntax, hangOf } from "@/components/ui/code";
import { Tabs, TabsContent, TabsList } from "@/components/ui/tabs";
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
/** An option's name as the file it would be written in. */
const fileOf = (name: string) =>
  `${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.md`;

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
export function DeployBody() {
  return (
    <>
      {OPTIONS.map((opt, i) => (
        <section
          key={opt.name}
          className="relative border-t border-rule odd:bg-paper-warm/40"
        >
          <MeanderDivider />
          <div className="mx-auto max-w-shell px-gutter py-16 lg:py-20">
            <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] lg:gap-16 xl:gap-24">
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
            <FramePanel className="bg-editor">
              <Tabs defaultValue={COMPARE[0].name}>
                {/* Each option is a file open in the editor, so the tab strip
                    is the one an editor would show. */}
                <TabsList className="overflow-x-auto bg-paper-warm/60">
                  <span aria-hidden className="flex items-center gap-1.5 px-3.5">
                    {[0, 1, 2].map((i) => (
                      <span key={i} className="size-[7px] rounded-full border border-rule" />
                    ))}
                  </span>
                  {COMPARE.map((c) => (
                    <TabsPrimitive.Trigger
                      key={c.name}
                      value={c.name}
                      className="relative -mb-px border-r border-rule px-3.5 py-2 font-mono text-[0.6875rem] whitespace-nowrap text-ink-faint transition-colors hover:text-ink-soft data-[state=active]:bg-editor data-[state=active]:text-ink data-[state=active]:before:absolute data-[state=active]:before:inset-x-0 data-[state=active]:before:top-0 data-[state=active]:before:h-px data-[state=active]:before:bg-accent"
                    >
                      {fileOf(c.name)}
                    </TabsPrimitive.Trigger>
                  ))}
                </TabsList>
                {COMPARE.map((c, i) => (
                  <TabsContent key={c.name} value={c.name}>
                    <div className="py-2.5 font-mono text-[0.75rem] leading-[1.75]">
                      {[
                        `# ${c.name}`,
                        "",
                        ...c.rows.map(([term, detail]) => `- **${term}**: ${detail}`),
                      ].map((line, n) => (
                        <CodeRow key={n} n={n + 1} hang={hangOf(line)}>
                          <Syntax text={line} lang="markdown" />
                        </CodeRow>
                      ))}
                    </div>
                    <div className="flex items-center justify-between border-t border-rule px-5 py-3.5">
                      <span className="kicker flex items-center gap-1.5 !text-[0.625rem] text-accent">
                        <MeanderMark size={9} />
                        {OPTIONS[i].dominion}
                      </span>
                      <Link
                        href={OPTIONS[i].href}
                        className="kicker link-sweep !text-[0.625rem] text-accent transition-colors hover:text-ink"
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
        <div className="mx-auto max-w-shell px-gutter py-16">
          <Reveal>
            <FramePanel className="bg-paper-warm/40">
              <div className="flex flex-col items-start gap-6 px-[clamp(1.5rem,3vw,3rem)] py-[clamp(2rem,3vw,2.75rem)] sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="font-display text-3xl font-light tracking-tight">
                    Put Pantheon to work.
                  </h2>
                  <p className="body-copy mt-2 max-w-xl text-ink-mute">
                    A 30-minute call. We map one job you already do by hand and
                    show you the audit log by the end of it.
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
