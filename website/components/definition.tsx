import { EngravedPlate } from "@/components/ui/engraved-plate";
import { FramePanel } from "@/components/ui/frame-panel";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { HERAKLES } from "@/lib/engravings/herakles";
import { cn } from "@/lib/utils";

// The definition behind the financial audit pipeline, written the way the
// authoring rules require: literal data, kind discriminators, refs by
// name@version, and no expression language anywhere.
const YAML = `kind: trigger
name: report.request
version: 1
source: webhook
emits: report.request@1

---

kind: task
name: gather
version: 1
runner:
  kind: agent
  spec: audit.analyst@3
input: report.request@1
output: report.spec@1
uses:
  - resource: ledger
    verbs: [query]
  - resource: receipts
    verbs: [get]
  - resource: fx_rates
    verbs: [request]
on: report.request@1
then: [render@1]
policy:
  timeout: 90s
  retry: 2
  idempotent: true

---

kind: task
name: render
version: 1
runner:
  kind: script
  runtime: python
  entry: render.main
input: report.spec@1
output: file@1`;

/** Keys recede, values carry the ink - the same hierarchy an editor gives you. */
function YamlLine({ line }: { line: string }) {
  if (line === "") return <span className="block h-[1.5em]" />;
  if (line === "---")
    return <span className="block text-ink-faint">{line}</span>;

  const match = line.match(/^(\s*-?\s*)([A-Za-z_][\w.]*)(:)(.*)$/);
  if (!match) return <span className="block text-ink-soft">{line}</span>;

  const [, prefix, key, colon, rest] = match;
  return (
    <span className="block">
      {prefix}
      <span className="text-ink-mute">{key}</span>
      {colon}
      <span className="text-ink">{rest}</span>
    </span>
  );
}

function Node({
  kind,
  name,
  className,
}: {
  kind: string;
  name: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 border border-rule bg-paper px-3.5 py-2.5",
        className
      )}
    >
      <span className="font-mono text-[12.5px] text-ink">{name}</span>
      <span className="kicker !text-[9px]">{kind}</span>
    </div>
  );
}

/** A derived edge: a hairline drop with the reference that produced it. */
function Edge({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 py-1.5 pl-3.5">
      <span aria-hidden className="h-6 w-px bg-rule" />
      <span className="kicker !text-[9px] text-accent">{label}</span>
    </div>
  );
}

const USES: [string, string][] = [
  ["ledger", "postgres · query"],
  ["receipts", "object store · get"],
  ["fx_rates", "http · request"],
];

const PRIMITIVES: [string, string][] = [
  ["Trigger", "cron · webhook · manual"],
  ["Task", "script · agent"],
  ["Resource", "postgres · object store · http"],
  ["Approval", "approvers · timeout"],
];

const VALUES: [string, string][] = [
  ["Text", "a body of words"],
  ["File", "content-addressed blob handle"],
  ["Table", "columns plus a row source"],
  ["Record", "typed against a registered schema"],
  ["Error", "typed failure, routed not thrown"],
];

/**
 * The authoring chapter. The claim that definitions are data is one a page
 * can show rather than assert, so this section puts the YAML next to the
 * graph compiled out of it and lets the reader check that no edge was ever
 * written by hand.
 */
export function Definition() {
  return (
    <section id="definitions" className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-20 lg:py-28">
        <Reveal className="flex items-start justify-between gap-10">
          <div className="max-w-2xl">
            <p className="kicker text-accent">iii &mdash; the labors</p>
            <h2 className="font-display mt-6 text-[clamp(2.25rem,4.5vw,3.5rem)] leading-[1.06] font-light tracking-tight">
              Workflows are data,{" "}
              <span className="headline-emph">not code.</span>
            </h2>
            <p className="lede-copy mt-6">
              A workflow is a set of YAML definitions that compile into a
              typed graph before anything runs. They diff in review like any
              other file, and a mismatched pair of tasks is caught when you
              plan, not at three in the morning when it runs.
            </p>
          </div>
          <div className="hidden shrink-0 xl:block">
            <EngravedPlate art={HERAKLES} preClassName="text-[3px] leading-[3.3px]" />
          </div>
        </Reveal>

        <div className="mt-12 grid gap-8 lg:grid-cols-[1.05fr_1fr] lg:gap-12">
          <Reveal delay={0.1}>
            <FramePanel className="bg-paper-warm/40">
              <div className="flex items-center justify-between border-b border-rule px-4 py-2">
                <span className="kicker !text-[10px]">
                  pipelines/audit.yaml
                </span>
                <span className="kicker !text-[10px] text-accent">
                  what you write
                </span>
              </div>
              <pre className="overflow-x-auto px-4 py-4 font-mono text-[11.5px] leading-[1.75] whitespace-pre">
                {YAML.split("\n").map((line, i) => (
                  <YamlLine key={i} line={line} />
                ))}
              </pre>
            </FramePanel>
          </Reveal>

          {/* The compiled graph is shorter than the source it came from, so
              it sticks while the definitions scroll past it. */}
          <Reveal delay={0.2} className="lg:sticky lg:top-28 lg:self-start">
            <FramePanel className="bg-paper-warm/40">
              <div className="flex items-center justify-between border-b border-rule px-4 py-2">
                <span className="kicker !text-[10px]">ptn apply</span>
                <span className="kicker !text-[10px] text-accent">
                  what gets built
                </span>
              </div>
              <div className="px-4 py-5">
                <Node kind="trigger · webhook" name="report.request@1" />
                <Edge label="derived from on:" />
                <Node kind="task · agent" name="gather@1" />

                {/* uses: refs become capability edges, drawn as a bracket
                    hanging off the task that declared them. */}
                <div className="mt-2 ml-3.5 border-l border-rule pl-4">
                  <p className="kicker !text-[9px] text-accent">
                    derived from uses:
                  </p>
                  <div className="mt-2 space-y-1.5">
                    {USES.map(([name, meta]) => (
                      <div
                        key={name}
                        className="flex items-baseline justify-between gap-3"
                      >
                        <span className="font-mono text-[12px] text-ink-soft">
                          {name}
                        </span>
                        <span className="kicker !text-[9px]">{meta}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <Edge label="derived from then:" />
                <Node kind="task · script" name="render@1" />
                <Edge label="declared output" />
                <Node kind="value · file" name="report.html" />
              </div>
              <p className="border-t border-rule px-4 py-3.5 body-copy-sm text-ink-mute">
                You never drew an edge. Every arrow above came out of an{" "}
                <span className="font-mono text-[13px] text-ink">on:</span>,{" "}
                <span className="font-mono text-[13px] text-ink">then:</span>,
                or{" "}
                <span className="font-mono text-[13px] text-ink">uses:</span>{" "}
                reference, which is why the graph and the files can never
                disagree.
              </p>
            </FramePanel>
          </Reveal>
        </div>

        {/* The closed vocabulary: the argument for why the engine stays the
            same size as your library of workflow types grows. */}
        <Reveal delay={0.15} className="mt-14">
          <div className="grid gap-6 sm:grid-cols-2">
            <FramePanel className="bg-paper-warm/20">
              <p className="kicker border-b border-rule px-4 py-2 !text-[10px] text-accent">
                four primitives &mdash; the whole vocabulary
              </p>
              <dl className="divide-y divide-rule">
                {PRIMITIVES.map(([term, variants]) => (
                  <div
                    key={term}
                    className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3"
                  >
                    <dt className="font-display text-lg font-medium">
                      {term}
                    </dt>
                    <dd className="kicker !text-[9px]">{variants}</dd>
                  </div>
                ))}
              </dl>
            </FramePanel>

            <FramePanel className="bg-paper-warm/20">
              <p className="kicker border-b border-rule px-4 py-2 !text-[10px] text-accent">
                five values &mdash; everything that crosses a seam
              </p>
              <dl className="divide-y divide-rule">
                {VALUES.map(([term, gloss]) => (
                  <div
                    key={term}
                    className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3"
                  >
                    <dt className="font-display text-lg font-medium">
                      {term}
                    </dt>
                    <dd className="kicker !text-[9px]">{gloss}</dd>
                  </div>
                ))}
              </dl>
            </FramePanel>
          </div>
          <p className="body-copy mt-6 max-w-3xl text-ink-mute">
            That is the entire vocabulary, and it is closed on purpose. All
            your business meaning lives in Records, checked against schemas
            you register, so the engine never grows a branch for your domain
            and your hundredth workflow type costs the same as your first.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
