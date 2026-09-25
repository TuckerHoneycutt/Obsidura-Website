"use client";

import { useEffect, useRef, useState } from "react";
import {
  AnimatePresence,
  motion,
  useInView,
  useReducedMotion,
} from "motion/react";
import {
  CodeRow,
  EditorTabs,
  StatusBar,
  Tokens,
  tokenize,
  type Token,
} from "@/components/ui/code";
import { FramePanel } from "@/components/ui/frame-panel";
import { cn } from "@/lib/utils";

type Requester = {
  id: string;
  role: string;
  /** The patients grant adds research consent on top of the ward. */
  consent: boolean;
  scans: boolean;
};

const REQUESTERS: Requester[] = [
  { id: "u_ellis", role: "attending, ward 3", consent: false, scans: true },
  { id: "u_rhodes", role: "research fellow", consent: true, scans: false },
];

const PROMPT = "Summarize this week’s admissions on ward 3.";

// Ward 3's 36 admissions this week. Twelve carry research consent, and
// twelve have a scan under scans/ward-3/ - the counts the audit trail shows.
const WARD_3 = [
  3001, 3002, 3004, 3005, 3006, 3007, 3009, 3010, 3011, 3012, 3013, 3014,
  3015, 3016, 3017, 3018, 3019, 3021, 3022, 3023, 3024, 3025, 3026, 3027,
  3028, 3029, 3030, 3031, 3032, 3033, 3034, 3035, 3036, 3037, 3038, 3040,
];
const RESEARCH = new Set([
  3002, 3006, 3011, 3014, 3017, 3021, 3025, 3029, 3031, 3034, 3037, 3040,
]);
const SCANNED = [
  3004, 3007, 3012, 3014, 3017, 3019, 3022, 3026, 3029, 3032, 3035, 3038,
];

const AUDIT: [string, string][] = [
  ["09:12:01", "grant   u_ellis    patients   query   row filter: ward = 3"],
  ["09:12:01", "scope   patients -> 36 rows in scope"],
  ["09:12:02", "grant   u_ellis    scans      get     key prefix: scans/ward-3/"],
  ["09:12:04", "grant   u_rhodes   patients   query   + consent = 'research'"],
  ["09:12:04", "scope   patients -> 12 rows in scope, 24 withheld"],
  ["09:12:05", "deny    u_rhodes   scans      get     no grant for this resource"],
];

/*
 * The whole sequence runs off one clock, in milliseconds. Each beat reads
 * the clock rather than owning a timer, so pausing, looping, and the
 * reduced-motion still frame are all just values of `t`.
 */
const TICK = 50;
const AT = {
  prompt: [0, 1300],
  /** The proxy starts evaluating the source rows, one tick mark each. */
  gate: 7300,
  gateStep: 35,
  /** The proxy decides the scans call. */
  gateScans: 8700,
  /** Only then does anything come back to the task. */
  rows: 9200,
  scans: 10100,
  audit: 11000,
  caption: 12800,
  fade: 16800,
  loop: 17400,
} as const;
/** The frame shown under reduced motion: everything settled. */
const STILL = AT.fade - 1;

const EASE = [0.22, 1, 0.36, 1] as const;

type TraceLine = { tokens: Token[]; at: readonly [number, number] } | null;

const t_ = (kind: Token["kind"], text: string): Token => ({ kind, text });
const call = (verb: string, target: string) => [
  t_("key", verb),
  t_("text", "  "),
  t_("string", target),
];
const scope = (key: string, rest: Token[]) => [
  t_("text", "  "),
  t_("keyword", key),
  t_("punct", ":"),
  ...rest,
];

/**
 * Each run's trace, as the file in its editor group. The two files are the
 * same line for line except where the grants differ; u_ellis keeps a blank
 * line where u_rhodes's extra clause sits so the groups stay aligned.
 */
function trace(r: Requester): TraceLine[] {
  return [
    { tokens: [t_("comment", "-- 01  the task sends, identical in both runs")], at: [1500, 1900] },
    { tokens: call("postgres.query", "patients"), at: [1900, 2400] },
    { tokens: tokenize("  select patient, reason", "sql"), at: [2400, 2850] },
    { tokens: tokenize("  from admissions where ward = 3", "sql"), at: [2850, 3350] },
    { tokens: call("s3.get", "scans/ward-3/"), at: [3350, 3700] },
    null,
    { tokens: [t_("comment", "-- 02  the proxy applies the grant")], at: [3950, 4300] },
    { tokens: call("grant", "patients · query"), at: [4300, 4600] },
    { tokens: scope("row filter", tokenize(" ward = 3", "sql")), at: [4600, 5000] },
    r.consent
      ? { tokens: tokenize("    and consent = 'research'", "sql"), at: [5200, 6000] }
      : null,
    { tokens: call("grant", "scans · get"), at: [6100, 6400] },
    r.scans
      ? { tokens: scope("key prefix", [t_("string", " scans/ward-3/")]), at: [6400, 6900] }
      : { tokens: [t_("text", "  "), t_("keyword", "deny"), t_("text", "  no grant for this resource")], at: [6400, 6900] },
    null,
    { tokens: [t_("comment", "-- 03  the proxy filters, then answers")], at: [6950, 7250] },
  ];
}

function typedChars(tokens: Token[], [start, end]: readonly [number, number], t: number) {
  const length = tokens.reduce((n, token) => n + token.text.length, 0);
  const progress = Math.min(1, Math.max(0, (t - start) / (end - start)));
  return Math.round(progress * length);
}

/** The line being typed at `t`, if any, and how far along it is. */
function cursorAt(lines: TraceLine[], t: number) {
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i];
    if (line && t >= line.at[0]) {
      return { line: i, col: typedChars(line.tokens, line.at, t) };
    }
  }
  return null;
}

/**
 * The proxy at work, between the call and the answer. It sees every source
 * row - it has to, to apply the filter - so the rows here are bare marks
 * with nothing readable on them, and the withheld ones stop at this line.
 * Nothing on the task's side of it ever shows a row the requester may not
 * see, not even for a frame.
 */
function Gate({ requester, t }: { requester: Requester; t: number }) {
  const evaluated = Math.max(
    0,
    Math.min(WARD_3.length, Math.floor((t - AT.gate) / AT.gateStep) + 1)
  );
  const passed = WARD_3.slice(0, evaluated).filter(
    (id) => !requester.consent || RESEARCH.has(id)
  ).length;
  const withheld = evaluated - passed;

  return (
    <div
      className={cn(
        "border-t border-rule transition-opacity duration-500",
        t >= AT.gate - 200 ? "opacity-100" : "opacity-0"
      )}
    >
      <div className="flex items-baseline justify-between gap-3 px-4 pt-2.5">
        <span className="font-mono text-[0.5625rem] tracking-[0.12em] text-ink-soft uppercase">
          proxy
        </span>
        <span className="font-mono text-[0.625rem] text-ink-faint">
          {evaluated} evaluated
        </span>
      </div>
      <div className="px-4 pt-2 pb-3 font-mono text-[0.6875rem] leading-[1.75] sm:text-[0.71875rem]">
        <div className="flex flex-wrap gap-[3px]">
          {WARD_3.map((id, i) => {
            const pass = !requester.consent || RESEARCH.has(id);
            return (
              <span
                key={id}
                className={cn(
                  "size-2.5 border transition-colors duration-300",
                  i >= evaluated
                    ? "border-rule"
                    : pass
                      ? "border-syn-string bg-syn-string"
                      : "border-ink-faint/60 bg-[repeating-linear-gradient(135deg,transparent_0_2px,var(--ink-faint)_2px_3px)] opacity-60"
                )}
              />
            );
          })}
        </div>
        <p className="mt-1.5">
          <span className="text-syn-string">{passed} passed</span>
          {requester.consent && (
            <span className="text-ink-mute"> · {withheld} withheld here</span>
          )}
        </p>
        <p
          className={cn(
            "transition-opacity duration-300",
            t >= AT.gateScans ? "opacity-100" : "opacity-0"
          )}
        >
          <span className="text-syn-key">scans · get</span>{" "}
          {requester.scans ? (
            <span className="text-syn-string">allowed</span>
          ) : (
            <span className="text-syn-keyword">denied, no grant</span>
          )}
        </p>
      </div>
    </div>
  );
}

function Group({ requester, t }: { requester: Requester; t: number }) {
  const lines = trace(requester);
  const cursor = cursorAt(lines, t);
  const typing = t < AT.gate;
  // Only rows the grant allows are ever rendered on the task's side.
  const allowed = WARD_3.filter((id) => !requester.consent || RESEARCH.has(id));
  const shownRows = allowed.filter((_, i) => t >= AT.rows + i * 30);

  return (
    <div className="min-w-0">
      <EditorTabs
        tabs={[`${requester.id}.trace`]}
        meta={requester.role}
        controls={false}
      />
      <div className="overflow-x-auto py-2.5 font-mono text-[0.6875rem] leading-[1.75] sm:text-[0.71875rem]">
        {lines.map((line, i) => (
          <CodeRow key={i} n={i + 1} active={cursor?.line === i && typing}>
            {line && (
              <Tokens
                tokens={line.tokens}
                upto={typedChars(line.tokens, line.at, t)}
                caret={cursor?.line === i && typing}
              />
            )}
          </CodeRow>
        ))}
      </div>

      <Gate requester={requester} t={t} />

      <div className="border-t border-rule">
        <div className="flex items-baseline justify-between gap-3 px-4 pt-2.5">
          <span className="font-mono text-[0.5625rem] tracking-[0.12em] text-ink-soft uppercase">
            returned to the task
          </span>
          <span className="font-mono text-[0.625rem] text-ink-faint">
            {shownRows.length} rows
          </span>
        </div>
        <div className="px-4 pt-2 pb-4 font-mono text-[0.6875rem] sm:text-[0.71875rem]">
          <ul className="grid h-[11.75rem] grid-cols-6 content-start gap-1 sm:h-[7.75rem] sm:grid-cols-9">
            <AnimatePresence mode="popLayout">
              {shownRows.map((id) => (
                <motion.li
                  key={id}
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.4, ease: EASE }}
                  className="h-7 border border-rule bg-paper-warm/60 text-center leading-7 text-syn-number"
                >
                  {id}
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>

          <div className="mt-3 min-h-[3.5rem] leading-[1.75]">
            <p className={cn("transition-opacity duration-500", t >= AT.scans ? "opacity-100" : "opacity-0")}>
              <span className="text-syn-key">scans/ward-3/</span>
            </p>
            <div className={cn("transition-opacity duration-500", t >= AT.scans ? "opacity-100" : "opacity-0")}>
              {requester.scans ? (
                <p className="flex flex-wrap gap-x-3 pl-2 text-syn-string">
                  {SCANNED.map((id) => (
                    <span key={id}>{id}.dcm</span>
                  ))}
                </p>
              ) : (
                <p className="pl-2 text-ink-mute">
                  nothing returned &mdash; refused at the proxy
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * The governance plate, played in an editor rather than operated: one prompt
 * issued by two people, their runs open side by side as a split editor. The
 * task sends the same call in both; the proxy applies a different grant;
 * different data comes back. The filtering happens in a proxy strip between
 * the call and the results, and u_rhodes's results only ever receive the
 * twelve rows in scope - no frame of the film shows the other twenty-four
 * on the task's side, because the product never puts them there. The audit
 * panel closes the loop.
 *
 * Plays only while on screen, can be paused, and under reduced motion shows
 * the settled final frame. The film itself is hidden from assistive tech,
 * which gets the same story as one paragraph.
 */
export function ScopeTrace() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.35 });
  const reduced = useReducedMotion();
  const [playing, setPlaying] = useState(true);
  const [clock, setClock] = useState(0);

  const running = inView && playing && !reduced;
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(
      () => setClock((c) => (c + TICK >= AT.loop ? 0 : c + TICK)),
      TICK
    );
    return () => window.clearInterval(id);
  }, [running]);

  const t = reduced ? STILL : clock;
  const promptTokens = [{ kind: "text" as const, text: PROMPT }];
  const promptTyping = t < AT.prompt[1] + 300;
  const auditShown = Math.max(0, Math.floor((t - AT.audit) / 260) + 1);
  const cursor = cursorAt(trace(REQUESTERS[1]), t);

  return (
    <FramePanel className="bg-editor" interactive={false}>
      <div className="flex items-center gap-3 border-b border-rule bg-paper-warm/60 py-2 pr-4 pl-3.5">
        <span aria-hidden className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="size-[7px] rounded-full border border-rule" />
          ))}
        </span>
        <span className="flex-1 text-center font-mono text-[0.625rem] text-ink-faint">
          governance &mdash; one prompt, two requesters
        </span>
        {!reduced && (
          <button
            type="button"
            onClick={() => setPlaying((p) => !p)}
            aria-label={playing ? "Pause the animation" : "Play the animation"}
            className="font-mono text-[0.625rem] text-ink-mute transition-colors hover:text-ink"
          >
            {playing ? "pause" : "play"}
          </button>
        )}
      </div>

      <p className="sr-only">
        The same prompt, &ldquo;{PROMPT}&rdquo;, is run for two people. In both
        runs the task sends the identical query for ward 3&rsquo;s admissions
        and the identical request for its scans. The proxy applies each
        person&rsquo;s grant. u_ellis, the ward&rsquo;s attending, is scoped to
        ward 3 and receives all 36 admissions and 12 scans. u_rhodes, a
        research fellow, is scoped to ward 3 with research consent and receives
        12 admissions; the other 24 are never sent, and the scans request is
        denied because u_rhodes holds no grant for it. Every decision is
        written to the audit log.
      </p>

      <div
        ref={ref}
        aria-hidden
        className={cn(
          "relative transition-opacity duration-500",
          t >= AT.fade ? "opacity-0" : "opacity-100"
        )}
      >
        {/* The prompt, entered the way you would run anything in an editor. */}
        <div className="border-b border-rule px-4 py-3">
          <p className="mx-auto flex max-w-2xl items-center gap-3 border border-rule bg-paper-warm/60 px-3 py-2 font-mono text-[0.75rem] sm:text-[0.8125rem]">
            <span className="text-syn-keyword">&gt;</span>
            <span className="min-w-0 truncate">
              <Tokens
                tokens={promptTokens}
                upto={typedChars(promptTokens, AT.prompt, t)}
                caret={promptTyping}
              />
            </span>
          </p>
        </div>

        <div className="grid divide-y divide-rule md:grid-cols-2 md:divide-x md:divide-y-0">
          {REQUESTERS.map((r) => (
            <Group key={r.id} requester={r} t={t} />
          ))}
        </div>

        <div className="border-t border-rule">
          <div className="flex gap-5 px-4 pt-2 font-mono text-[0.5625rem] tracking-[0.12em] uppercase">
            <span className="border-b border-accent pb-1.5 text-ink">
              audit log
            </span>
            <span className="text-ink-faint">terminal</span>
          </div>
          <div className="overflow-x-auto px-4 pt-1.5 pb-3">
            {AUDIT.map(([time, text], i) => {
              const [, verb, rest] = text.match(/^(\S+)(.*)$/)!;
              return (
                <p
                  key={time + text}
                  className={cn(
                    "flex gap-3 py-0.5 font-mono text-[0.6875rem] whitespace-pre transition-opacity duration-300 sm:text-[0.71875rem]",
                    i < auditShown ? "opacity-100" : "opacity-0"
                  )}
                >
                  <span className="shrink-0 text-ink-faint">[{time}]</span>
                  <span>
                    <span className={verb === "deny" ? "text-syn-keyword" : "text-syn-key"}>
                      {verb}
                    </span>
                    <span className="text-ink-soft">{rest}</span>
                  </span>
                </p>
              );
            })}
          </div>
        </div>

        {/* A notification toast, where an editor would put one. */}
        <div
          className={cn(
            "border-t border-rule bg-paper-warm px-4 py-3 transition-all duration-500 md:absolute md:right-4 md:bottom-4 md:max-w-sm md:border md:shadow-[0_8px_24px_rgba(0,0,0,0.35)]",
            t >= AT.caption
              ? "translate-y-0 opacity-100"
              : "opacity-0 md:translate-y-2"
          )}
        >
          <p className="flex gap-2.5">
            <span className="mt-px font-mono text-[0.75rem] text-syn-key">i</span>
            <span className="body-copy-sm !text-[0.875rem] text-ink-soft">
              Nothing was masked. The proxy withheld u_rhodes&rsquo;s other
              twenty-four rows before anything came back, so they were never
              in the run to leak, unmask, or summarize by mistake.
            </span>
          </p>
        </div>
      </div>

      <StatusBar
        left="run as u_ellis · u_rhodes"
        right={
          <>
            <span>
              {cursor && t < AT.gate
                ? `Ln ${cursor.line + 1}, Col ${cursor.col + 1}`
                : `${Math.min(auditShown, AUDIT.length)} decisions logged`}
            </span>
            <span className="hidden sm:inline">UTF-8</span>
            <span>Trace</span>
          </>
        }
      />
    </FramePanel>
  );
}
