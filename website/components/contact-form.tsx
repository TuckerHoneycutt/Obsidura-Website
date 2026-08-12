"use client";

import { useState, type FormEvent } from "react";
import type { ContactState } from "@/lib/contact";
import { FramePanel } from "@/components/ui/frame-panel";
import { cn } from "@/lib/utils";

const initialState: ContactState = { ok: false, message: "" };

const fieldClass =
  "w-full border border-rule bg-paper px-3.5 py-3 font-mono text-sm text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-accent-deep";

const labelClass = "kicker mb-2 block !text-[10px]";

export function ContactForm() {
  const [state, setState] = useState<ContactState>(initialState);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);

    const form = event.currentTarget;
    const formData = new FormData(form);

    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formData.get("name"),
          email: formData.get("email"),
          company: formData.get("company"),
          message: formData.get("message"),
          company_url: formData.get("company_url"),
        }),
      });

      const nextState = (await response.json()) as ContactState;
      setState(nextState);

      if (nextState.ok) {
        form.reset();
      }
    } catch {
      setState({
        ok: false,
        message: "Could not send your message. Please try again shortly.",
      });
    } finally {
      setPending(false);
    }
  }

  if (state.ok) {
    return (
      <FramePanel className="bg-paper-warm/40 px-6 py-10 sm:px-8">
        <p className="kicker text-accent">received</p>
        <p className="font-display mt-4 text-3xl font-light tracking-tight">
          Message sent.
        </p>
        <p className="body-copy mt-3 max-w-md">
          {state.message}
        </p>
      </FramePanel>
    );
  }

  return (
    <FramePanel className="bg-paper-warm/40">
      <form
        onSubmit={handleSubmit}
        action="/api/contact"
        method="post"
        className="relative flex flex-col gap-6 px-6 py-8 sm:px-8"
      >
        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <label htmlFor="name" className={labelClass}>
              Name
            </label>
            <input
              id="name"
              name="name"
              type="text"
              required
              autoComplete="name"
              className={cn(
                fieldClass,
                state.fieldErrors?.name && "border-accent"
              )}
            />
            {state.fieldErrors?.name ? (
              <p className="mt-2 font-mono text-[12px] text-ink-mute">
                {state.fieldErrors.name}
              </p>
            ) : null}
          </div>
          <div>
            <label htmlFor="email" className={labelClass}>
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              className={cn(
                fieldClass,
                state.fieldErrors?.email && "border-accent"
              )}
            />
            {state.fieldErrors?.email ? (
              <p className="mt-2 font-mono text-[12px] text-ink-mute">
                {state.fieldErrors.email}
              </p>
            ) : null}
          </div>
        </div>

        <div>
          <label htmlFor="company" className={labelClass}>
            Company <span className="text-ink-faint">(optional)</span>
          </label>
          <input
            id="company"
            name="company"
            type="text"
            autoComplete="organization"
            className={fieldClass}
          />
        </div>

        <div>
          <label htmlFor="message" className={labelClass}>
            Message
          </label>
          <textarea
            id="message"
            name="message"
            required
            rows={6}
            className={cn(
              fieldClass,
              "resize-y min-h-[9rem]",
              state.fieldErrors?.message && "border-accent"
            )}
          />
          {state.fieldErrors?.message ? (
            <p className="mt-2 font-mono text-[12px] text-ink-mute">
              {state.fieldErrors.message}
            </p>
          ) : null}
        </div>

        {/* Honeypot — hidden from humans */}
        <div aria-hidden className="pointer-events-none absolute -left-[9999px] opacity-0">
          <label htmlFor="company_url">Company URL</label>
          <input
            id="company_url"
            name="company_url"
            type="text"
            tabIndex={-1}
            autoComplete="off"
          />
        </div>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          {state.message ? (
            <p
              aria-live="polite"
              className="font-mono text-[13px] text-ink-mute"
            >
              {state.message}
            </p>
          ) : (
            <p className="font-mono text-[13px] text-ink-faint">
              We typically reply within one business day.
            </p>
          )}
          <button
            type="submit"
            disabled={pending}
            className="kicker shrink-0 bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft disabled:cursor-wait disabled:opacity-60"
          >
            {pending ? "Sending..." : "Send message"}
          </button>
        </div>
      </form>
    </FramePanel>
  );
}
