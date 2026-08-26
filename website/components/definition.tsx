"use client";

import { useState } from "react";
import { FramePanel } from "@/components/ui/frame-panel";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { cn } from "@/lib/utils";

/**
 * Every element of the compiled graph, and the reference in the source that
 * produced it. Highlighting is keyed on these, so the page can only ever
 * claim a link the definition actually declares.
 */
type Ref =
  | "trigger"
  | "gather"
  | "ledger"
  | "receipts"
  | "fx_rates"
  | "render"
  | "output";

type Line = { text: string; ref?: Ref };

// The definition behind the financial audit pipeline, written the way the
// authoring rules require: literal data, kind discriminators, refs by
// name@version, and no expression language anywhere.
const YAML: Line[] = [
  { text: "kind: trigger" },
  { text: "name: report.request", ref: "trigger" },
  { text: "version: 1" },
  { text: "source: webhook" },
  { text: "emits: report.request@1", ref: "trigger" },
  { text: "" },
  { text: "---" },
  { text: "" },
  { text: "kind: task" },
  { text: "name: gather", ref: "gather" },
  { text: "version: 1" },
  { text: "runner:" },
  { text: "  kind: agent" },
  { text: "  spec: audit.analyst@3" },
  { text: "input: report.request@1" },
  { text: "output: report.spec@1" },
  { text: "uses:" },
  { text: "  - resource: ledger", ref: "ledger" },
  { text: "    verbs: [query]", ref: "ledger" },
  { text: "  - resource: receipts", ref: "receipts" },
  { text: "    verbs: [get]", ref: "receipts" },
  { text: "  - resource: fx_rates", ref: "fx_rates" },
  { text: "    verbs: [request]", ref: "fx_rates" },
  { text: "on: report.request@1", ref: "trigger" },
  { text: "then: [render@1]", ref: "render" },
  { text: "policy:" },
  { text: "  timeout: 90s" },
  { text: "  retry: 2" },
  { text: "  idempotent: true" },
  { text: "" },
  { text: "---" },
  { text: "" },
  { text: "kind: task" },
  { text: "name: render", ref: "render" },
  { text: "version: 1" },
  { text: "runner:" },
  { text: "  kind: script" },
  { text: "  runtime: python" },
  { text: "  entry: render.main" },
  { text: "input: report.spec@1" },
  { text: "output: file@1", ref: "output" },
];

/** Keys recede, values carry the ink - the same hierarchy an editor gives you. */
function YamlText({ text }: { text: string }) {
  if (text === "---") return <span className="text-ink-faint">{text}</span>;

  const match = text.match(/^(\s*-?\s*)([A-Za-z_][\w.]*)(:)(.*)$/);
  if (!match) return <span className="text-ink-soft">{text}</span>;

  const [, prefix, key, colon, rest] = match;
  return (
    <>
      {prefix}
      <span className="text-ink-mute">{key}</span>
      {colon}
      <span className="text-ink">{rest}</span>
    </>
  );
}

/** Shared highlight treatment for a linked source line or graph element. */
const LIT = "bg-accent-pale text-ink";

function YamlRow({
  line,
  active,
  onActivate,
}: {
  line: Line;
  active: boolean;
  onActivate: (ref: Ref | null) => void;
}) {
  if (line.text === "") return <span className="block h-[1.5em]" />;

  if (!line.ref) {
    return (
      <span className="block">
        <YamlText text={line.text} />
      </span>
    );
  }

  const ref = line.ref;
  // The source side is the focusable one: buttons here keep the link
  // reachable without a pointer, while the graph side reacts to hover only,
  // which would otherwise double the tab stops for the same information.
  return (
    <button
      type="button"
      onMouseEnter={() => onActivate(ref)}
      onMouseLeave={() => onActivate(null)}
      onFocus={() => onActivate(ref)}
      onBlur={() => onActivate(null)}
      className={cn(
        // font-[inherit] matters: a button does not take the pre's face.
        "-mx-2 block w-[calc(100%+1rem)] cursor-default px-2 text-left font-[inherit] text-[inherit] leading-[inherit] transition-colors",
        active && LIT
      )}
    >
      <YamlText text={line.text} />
    </button>
  );
}

function Node({
  kind,
  name,
  refId,
  active,
  onActivate,
}: {
  kind: string;
  name: string;
  refId: Ref;
  active: boolean;
  onActivate: (ref: Ref | null) => void;
}) {
  // Not focusable by design - see YamlRow. The graph reflects the source.
  return (
    <div
      onMouseEnter={() => onActivate(refId)}
      onMouseLeave={() => onActivate(null)}
      className={cn(
        "flex items-center justify-between gap-4 border px-3.5 py-2.5 transition-colors",
        active ? "border-accent-deep bg-accent-pale" : "border-rule bg-paper"
      )}
    >
      <span className="font-mono text-[12.5px] text-ink">{name}</span>
      <span className="kicker !text-[9px]">{kind}</span>
    </div>
  );
}

/** A derived edge: a hairline drop with the reference that produced it. */
function Edge({ label, active }: { label: string; active: boolean }) {
  return (
    <div className="flex items-center gap-2.5 py-1.5 pl-3.5">
      <span
        aria-hidden
        className={cn(
          "h-6 w-px transition-colors",
          active ? "bg-accent" : "bg-rule"
        )}
      />
      <span
        className={cn(
          "kicker !text-[9px] transition-colors",
          active ? "!text-ink" : "text-accent"
        )}
      >
        {label}
      </span>
    </div>
  );
}

const USES: { ref: Ref; name: string; meta: string }[] = [
  { ref: "ledger", name: "ledger", meta: "postgres · query" },
  { ref: "receipts", name: "receipts", meta: "object store · get" },
  { ref: "fx_rates", name: "fx_rates", meta: "http · request" },
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
 * graph compiled out of it - and hovering either side lights up the other,
 * which is the whole argument for deriving edges instead of drawing them.
 */
export function WorkflowsBody() {
  const [active, setActive] = useState<Ref | null>(null);
  const lit = (ref: Ref) => active === ref;

  return (
    <section className="relative border-t border-rule bg-paper-warm/60">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <div className="grid gap-8 lg:grid-cols-[1.05fr_1fr] lg:gap-12">
          <Reveal delay={0.1}>
            <FramePanel className="bg-paper">
              <div className="flex items-center justify-between border-b border-rule px-4 py-2">
                <span className="kicker !text-[10px]">
                  pipelines/audit.yaml
                </span>
                <span className="kicker !text-[10px] text-accent">
                  what you write
                </span>
              </div>
              <pre className="overflow-x-auto px-4 py-4 font-mono text-[11.5px] leading-[1.75] whitespace-pre">
                {YAML.map((line, i) => (
                  <YamlRow
                    key={i}
                    line={line}
                    active={!!line.ref && lit(line.ref)}
                    onActivate={setActive}
                  />
                ))}
              </pre>
            </FramePanel>
          </Reveal>

          {/* The compiled graph is shorter than the source it came from, so
              it sticks while the definitions scroll past it. */}
          <Reveal delay={0.2} className="lg:sticky lg:top-28 lg:self-start">
            <FramePanel className="bg-paper">
              <div className="flex items-center justify-between border-b border-rule px-4 py-2">
                <span className="kicker !text-[10px]">ptn apply</span>
                <span className="kicker !text-[10px] text-accent">
                  what gets built
                </span>
              </div>
              <div className="px-4 py-5">
                <Node
                  kind="trigger · webhook"
                  name="report.request@1"
                  refId="trigger"
                  active={lit("trigger")}
                  onActivate={setActive}
                />
                <Edge label="derived from on:" active={lit("trigger")} />
                <Node
                  kind="task · agent"
                  name="gather@1"
                  refId="gather"
                  active={lit("gather")}
                  onActivate={setActive}
                />

                {/* uses: refs become capability edges, drawn as a bracket
                    hanging off the task that declared them. */}
                <div
                  className={cn(
                    "mt-2 ml-3.5 border-l pl-4 transition-colors",
                    USES.some((u) => lit(u.ref))
                      ? "border-accent"
                      : "border-rule"
                  )}
                >
                  <p className="kicker !text-[9px] text-accent">
                    derived from uses:
                  </p>
                  <div className="mt-2 space-y-1.5">
                    {USES.map((use) => (
                      <div
                        key={use.ref}
                        onMouseEnter={() => setActive(use.ref)}
                        onMouseLeave={() => setActive(null)}
                        className={cn(
                          "-mx-1.5 flex items-baseline justify-between gap-3 px-1.5 py-0.5 transition-colors",
                          lit(use.ref) && LIT
                        )}
                      >
                        <span className="font-mono text-[12px] text-ink-soft">
                          {use.name}
                        </span>
                        <span className="kicker !text-[9px]">{use.meta}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <Edge label="derived from then:" active={lit("render")} />
                <Node
                  kind="task · script"
                  name="render@1"
                  refId="render"
                  active={lit("render")}
                  onActivate={setActive}
                />
                <Edge label="declared output" active={lit("output")} />
                <Node
                  kind="value · file"
                  name="report.html"
                  refId="output"
                  active={lit("output")}
                  onActivate={setActive}
                />
              </div>
              <p className="body-copy-sm border-t border-rule px-4 py-3.5 text-ink-mute">
                No edges are drawn by hand. Every arrow above comes from an{" "}
                <span className="font-mono text-[13px] text-ink">on:</span>,{" "}
                <span className="font-mono text-[13px] text-ink">then:</span>,
                or{" "}
                <span className="font-mono text-[13px] text-ink">uses:</span>{" "}
                reference &mdash; hover either side to see which.
              </p>
            </FramePanel>
          </Reveal>
        </div>

        {/* The closed vocabulary: the argument for why the engine stays the
            same size as your library of workflow types grows. */}
        <Reveal delay={0.15} className="mt-14">
          <div className="grid gap-6 sm:grid-cols-2">
            <FramePanel className="bg-paper">
              <p className="kicker border-b border-rule px-4 py-2 !text-[10px] text-accent">
                four primitives
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

            <FramePanel className="bg-paper">
              <p className="kicker border-b border-rule px-4 py-2 !text-[10px] text-accent">
                five values &mdash; everything passed between tasks
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
            That is the entire vocabulary, and it is closed on purpose. Your
            business data lives in Records, checked against schemas you
            register, so the engine never needs custom code for your domain
            and the cost of adding workflow types stays flat.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
