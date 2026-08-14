"use client";

import type { ReactNode } from "react";
import * as HoverCardPrimitive from "@radix-ui/react-hover-card";

/**
 * The system's vocabulary, defined once in plain words. A term used in
 * running copy or a log line links here, so the jargon can stay short on
 * the page and still be explained on demand.
 */
const GLOSSARY = {
  proxy: {
    title: "the proxy",
    plain:
      "The one door out. It holds every credential, checks each request against what the asker may see, fetches the data itself, and writes the decision down. The agent only ever talks to the proxy.",
  },
  shape: {
    title: "the declared shape",
    plain:
      "The form a result must take, agreed before anything runs — fields, types, and all. A result that does not match it does not pass.",
  },
  envelope: {
    title: "the envelope",
    plain:
      "The wrapper around a step's result: the validated data plus the run, task, attempt, and cost it came from. Nothing moves between steps outside one.",
  },
  "run log": {
    title: "the run log",
    plain:
      "One append-only record of everything a run did. The status page, the audit trail, approvals, and crash recovery all read from the same log.",
  },
  grant: {
    title: "a grant",
    plain:
      "A permission written down: this person, this resource, these verbs, this scope — a row filter, a key prefix, a URL allowlist. Minted for the run and checked on every call.",
  },
} as const;

export type TermKey = keyof typeof GLOSSARY;

/**
 * Wraps a word in running copy with a hover-card definition. The trigger
 * inherits the surrounding font, so it works in body copy and in the mono
 * log lines alike; a dotted underline is the only mark it leaves. Opens
 * on hover and on keyboard focus. On touch, the underline simply reads as
 * emphasis - the page never depends on the card being seen.
 */
export function Term({
  t,
  children,
}: {
  t: TermKey;
  children: ReactNode;
}) {
  const entry = GLOSSARY[t];
  return (
    <HoverCardPrimitive.Root openDelay={150} closeDelay={100}>
      <HoverCardPrimitive.Trigger asChild>
        <span
          tabIndex={0}
          className="cursor-help underline decoration-ink-faint decoration-dotted underline-offset-4 transition-colors hover:decoration-ink"
        >
          {children}
        </span>
      </HoverCardPrimitive.Trigger>
      <HoverCardPrimitive.Portal>
        <HoverCardPrimitive.Content
          side="top"
          align="start"
          sideOffset={8}
          collisionPadding={16}
          className="term-card z-[90] max-w-xs border border-rule bg-paper px-4 py-3.5"
        >
          <p className="kicker !text-[10px] text-accent">{entry.title}</p>
          <p className="body-copy-sm mt-2 text-ink-soft">{entry.plain}</p>
        </HoverCardPrimitive.Content>
      </HoverCardPrimitive.Portal>
    </HoverCardPrimitive.Root>
  );
}
