"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { EngravedPlate } from "@/components/ui/engraved-plate";
import { FramePanel } from "@/components/ui/frame-panel";
import { Reveal } from "@/components/ui/reveal";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { ATHENA_OWL } from "@/lib/engravings/athena-owl";
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
  { kind: "plan", time: "21:04:03", text: "job received - reconcile payout batches vs ledger (week 30)" },
  { kind: "tool", time: "21:04:04", text: "postgres.query   SELECT id, amount FROM ledger_entries WHERE week = 30" },
  { kind: "ok", time: "21:04:04", text: "1,284 rows in 41ms" },
  { kind: "tool", time: "21:04:05", text: "stripe.payouts.list   interval = 2026-07-20 .. 2026-07-26" },
  { kind: "ok", time: "21:04:06", text: "96 payouts fetched - schema validated" },
  { kind: "model", time: "21:04:08", text: "matching payouts to ledger entries - 93 exact, 3 ambiguous" },
  { kind: "tool", time: "21:04:09", text: "slack.post   #finance-approvals - 3 items need review" },
  { kind: "escalate", time: "21:04:09", text: "escalated 3/96 to human queue with full decision trace" },
  { kind: "ok", time: "21:04:10", text: "93 entries reconciled - audit log sealed" },
  { kind: "done", time: "21:04:10", text: "run complete in 2m 14s - replay id run_8f3k2c" },
];

const LINE_MS = 850;
const HOLD_MS = 4200;

export function AgentRun() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (media.matches) {
      setCount(RUN.length);
      return;
    }
    const tick = () => {
      setCount((c) => {
        if (c >= RUN.length) return c;
        return c + 1;
      });
    };
    let interval = window.setInterval(tick, LINE_MS);
    // Once complete, hold, then restart the loop.
    const loop = window.setInterval(() => {
      setCount((c) => (c >= RUN.length ? 0 : c));
    }, RUN.length * LINE_MS + HOLD_MS);
    return () => {
      window.clearInterval(interval);
      window.clearInterval(loop);
    };
  }, []);

  return (
    <section className="relative border-t border-rule">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <Reveal>
          <div className="flex items-end justify-between gap-6">
            <p className="kicker text-accent">what a labor looks like</p>
            <div className="hidden sm:block">
              <EngravedPlate art={ATHENA_OWL} />
            </div>
          </div>
        </Reveal>
        <Reveal delay={0.1} className="mt-8">
          <FramePanel className="bg-paper-warm/40">
            <div className="flex items-center justify-between border-b border-rule px-4 py-2">
              <span className="kicker">live run - payout reconciliation</span>
              <span className="kicker text-accent">mnemosyne - audit log</span>
            </div>
            <div className="h-[300px] overflow-hidden px-4 py-3 sm:h-[280px]">
              {RUN.slice(0, count).map((line, i) => (
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
        </Reveal>
      </div>
    </section>
  );
}
