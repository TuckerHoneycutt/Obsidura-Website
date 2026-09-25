"use client";

import { useState } from "react";
import {
  CodeRow,
  EditorTabs,
  StatusBar,
  Syntax,
  fileStatus,
} from "@/components/ui/code";
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

/** Highlight treatment for a graph element linked to the source. */
const LIT = "bg-accent-pale text-ink";

function YamlRow({
  n,
  line,
  active,
  onActivate,
}: {
  n: number;
  line: Line;
  active: boolean;
  onActivate: (ref: Ref | null) => void;
}) {
  const text = <Syntax text={line.text} lang="yaml" />;
  if (!line.ref) return <CodeRow n={n}>{text}</CodeRow>;

  const ref = line.ref;
  // The source side is the focusable one: buttons here keep the link
  // reachable without a pointer, while the graph side reacts to hover only,
  // which would otherwise double the tab stops for the same information.
  return (
    <CodeRow n={n} active={active}>
      <button
        type="button"
        onMouseEnter={() => onActivate(ref)}
        onMouseLeave={() => onActivate(null)}
        onFocus={() => onActivate(ref)}
        onBlur={() => onActivate(null)}
        // font-[inherit] matters: a button does not take the code's face.
        className="w-full cursor-default text-left font-[inherit] leading-[inherit] whitespace-pre"
      >
        {text}
      </button>
    </CodeRow>
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
      <span className="font-mono text-[0.78125rem] text-ink">{name}</span>
      <span className="kicker !text-[0.6875rem]">{kind}</span>
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
          "kicker !text-[0.6875rem] transition-colors",
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
  ["Text", "plain text"],
  ["File", "a file, passed by handle"],
  ["Table", "rows and columns, passed by handle"],
  ["Record", "structured data, checked against a schema"],
  ["Error", "a typed failure"],
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
  const firstLit = active ? YAML.findIndex((l) => l.ref === active) : -1;

  return (
    <section className="relative border-t border-rule bg-paper-warm/60">
      <MeanderDivider />
      <div className="mx-auto max-w-shell px-gutter py-16 lg:py-20">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:gap-12 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,0.95fr)] xl:gap-10">
          <Reveal delay={0.1}>
            <FramePanel className="bg-editor">
              <EditorTabs
                tabs={["audit.yaml", "render.py"]}
                meta="what you write"
              />
              <div className="overflow-x-auto py-2.5 font-mono text-[0.8125rem] leading-[1.75]">
                {YAML.map((line, i) => (
                  <YamlRow
                    key={i}
                    n={i + 1}
                    line={line}
                    active={!!line.ref && lit(line.ref)}
                    onActivate={setActive}
                  />
                ))}
              </div>
              <StatusBar
                left={
                  firstLit >= 0
                    ? `Ln ${firstLit + 1}, Col 1 · ${YAML.filter((l) => l.ref === active).length} lines reference ${active}`
                    : "pipelines/audit.yaml"
                }
                right={fileStatus("yaml")}
              />
            </FramePanel>
          </Reveal>

          {/* The compiled graph is shorter than the source it came from, so
              it sticks while the definitions scroll past it. */}
          <Reveal delay={0.2} className="lg:sticky lg:top-28 lg:self-start">
            <FramePanel className="bg-paper">
              <div className="flex items-center justify-between border-b border-rule px-4 py-2">
                <span className="kicker !text-[0.71875rem]">ptn apply</span>
                <span className="kicker !text-[0.71875rem] text-accent">
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
                  <p className="kicker !text-[0.6875rem] text-accent">
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
                        <span className="font-mono text-[0.75rem] text-ink-soft">
                          {use.name}
                        </span>
                        <span className="kicker !text-[0.6875rem]">{use.meta}</span>
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
                <span className="font-mono text-[0.8125rem] text-ink">on:</span>,{" "}
                <span className="font-mono text-[0.8125rem] text-ink">then:</span>,
                or{" "}
                <span className="font-mono text-[0.8125rem] text-ink">uses:</span>{" "}
                reference &mdash; hover either side to see which.
              </p>
            </FramePanel>
          </Reveal>

          {/* The closed vocabulary: the argument for why the engine stays the
              same size as your library of workflow types grows. */}
          <Reveal
            delay={0.15}
            className="mt-6 lg:col-span-2 lg:mt-2 xl:col-span-1 xl:mt-0"
          >
            <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-1">
              <FramePanel className="bg-paper">
                <p className="kicker border-b border-rule px-4 py-2 !text-[0.71875rem] text-accent">
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
                      <dd className="kicker !text-[0.6875rem]">{variants}</dd>
                    </div>
                  ))}
                </dl>
              </FramePanel>

              <FramePanel className="bg-paper">
                <p className="kicker border-b border-rule px-4 py-2 !text-[0.71875rem] text-accent">
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
                      <dd className="kicker !text-[0.6875rem]">{gloss}</dd>
                    </div>
                  ))}
                </dl>
              </FramePanel>
            </div>
            <p className="body-copy mt-6 max-w-3xl text-ink-mute">
              That is the entire vocabulary, and it is closed on purpose. Your
              business data lives in Records, checked against schemas you
              register, so the engine never needs custom code for your domain
              and adding more workflows never changes the engine.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
