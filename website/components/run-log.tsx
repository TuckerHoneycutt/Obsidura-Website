"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { motion } from "motion/react";
import { FramePanel } from "@/components/ui/frame-panel";
import { cn } from "@/lib/utils";

type LineKind = "plan" | "tool" | "ok" | "model" | "escalate" | "done";

type LogLine = {
  kind: LineKind;
  time: string;
  text: string;
};

// Monochrome palette: kinds are distinguished by brightness and weight only.
const KIND_STYLE: Record<LineKind, string> = {
  plan: "text-accent",
  tool: "text-ink-soft",
  ok: "text-ink-mute",
  model: "text-ink font-semibold",
  escalate: "text-ink underline underline-offset-4",
  done: "text-accent",
};

const RUN: LogLine[] = [
  { kind: "plan", time: "21:04:03", text: "webhook report.request   {prompt, requester: u_ellis}" },
  { kind: "ok", time: "21:04:03", text: "run opened - grants minted for u_ellis, proxy socket bound" },
  { kind: "tool", time: "21:04:04", text: "postgres.query   ledger_entries   row filter: entity = 'north'" },
  { kind: "ok", time: "21:04:04", text: "1,284 rows in scope - handed back as a table handle" },
  { kind: "tool", time: "21:04:05", text: "s3.get   receipts/2026-q2/   key prefix scope enforced" },
  { kind: "escalate", time: "21:04:05", text: "receipts/2026-q1/ denied for u_ellis - decision written to the log" },
  { kind: "tool", time: "21:04:06", text: "http.request   fx-rates   url allowlist checked" },
  { kind: "model", time: "21:04:08", text: "agent task composing a ReportSpec against report.spec@1" },
  { kind: "ok", time: "21:04:09", text: "output failed validation - truncated diff returned, attempt 1 of 2" },
  { kind: "ok", time: "21:04:09", text: "ReportSpec valid - record sealed into the envelope" },
  { kind: "tool", time: "21:04:10", text: "render task   composing the site from the template library" },
  { kind: "done", time: "21:04:10", text: "file artifact written - self-contained, snapshot baked in" },
];

const LINE_MS = 850;
const HOLD_MS = 4200;

const QUERY = "(prefers-reduced-motion: reduce)";

/**
 * Subscribed rather than read into state in an effect, so the preference is
 * available on the first client render and a mid-session change is picked
 * up. The server snapshot is false: markup matches the animated case, which
 * starts empty anyway.
 */
function usePrefersReducedMotion() {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(QUERY);
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    },
    () => window.matchMedia(QUERY).matches,
    () => false
  );
}

/**
 * The append-only run log, replayed. Every claim the governance chapter
 * makes - scope decisions, the repair loop, the sealed envelope - is a line
 * in this table rather than a separate subsystem.
 */
export function RunLog() {
  const [count, setCount] = useState(0);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    if (reduced) return;
    const interval = window.setInterval(() => {
      setCount((c) => (c >= RUN.length ? c : c + 1));
    }, LINE_MS);
    // Once complete, hold, then restart the loop.
    const loop = window.setInterval(
      () => setCount((c) => (c >= RUN.length ? 0 : c)),
      RUN.length * LINE_MS + HOLD_MS
    );
    return () => {
      window.clearInterval(interval);
      window.clearInterval(loop);
    };
  }, [reduced]);

  // Reduced motion gets the finished log rather than a stalled empty panel.
  const shown = reduced ? RUN.length : count;

  return (
    <FramePanel className="bg-paper-warm/40">
      <div className="flex items-center justify-between border-b border-rule px-4 py-2">
        <span className="kicker !text-[10px]">
          live run &mdash; financial audit
        </span>
        <span className="kicker !text-[10px] text-accent">
          run_events &mdash; append-only
        </span>
      </div>
      <div className="h-[300px] overflow-hidden px-4 py-3 sm:h-[280px]">
        {RUN.slice(0, shown).map((line, i) => (
          <motion.p
            key={`${line.time}-${i}`}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            className="flex gap-3 py-0.5 font-mono text-[11px] leading-relaxed sm:text-[12.5px]"
          >
            <span className="shrink-0 text-ink-faint">[{line.time}]</span>
            <span
              className={cn(
                "w-16 shrink-0 uppercase tracking-wider",
                KIND_STYLE[line.kind]
              )}
            >
              {line.kind}
            </span>
            <span className="text-ink-soft">{line.text}</span>
          </motion.p>
        ))}
        <p className="flex gap-3 py-0.5 font-mono text-[12.5px]">
          <span className="animate-pulse text-accent">&#9608;</span>
        </p>
      </div>
    </FramePanel>
  );
}
