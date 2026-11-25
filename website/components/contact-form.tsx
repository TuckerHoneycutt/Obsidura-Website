"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ContactState } from "@/lib/contact";
import { FramePanel } from "@/components/ui/frame-panel";
import { Input, Textarea } from "@/components/ui/input";
import { StatefulButton } from "@/components/ui/stateful-button";
import { cn } from "@/lib/utils";
import {
  TurnstileWidget,
  type TurnstileHandle,
} from "@/components/turnstile-widget";

const initialState: ContactState = { ok: false, message: "" };

const fieldClass =
  // No outline-none here: the border shift alone was the only focus signal,
  // and it is far too quiet to navigate a form by.
  "w-full border border-rule bg-paper px-3.5 py-3 font-mono text-sm text-ink transition-colors placeholder:text-ink-faint focus:border-accent-deep";

const labelClass = "kicker mb-2 block !text-[10px]";

export function ContactForm() {
  const [state, setState] = useState<ContactState>(initialState);
  const [pending, setPending] = useState(false);
  const [token, setToken] = useState("");
  const [verifyUnavailable, setVerifyUnavailable] = useState(false);
  const turnstileRef = useRef<TurnstileHandle>(null);
  // Set after mount so the server can drop submissions no person could type.
  const mountedAt = useRef(0);
  useEffect(() => {
    mountedAt.current = Date.now();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!token) {
      setState({
        ok: false,
        message: verifyUnavailable
          ? "Verification could not load. Please email contact@obsidura.com instead."
          : "Please wait for the verification check to finish, then send again.",
      });
      return;
    }

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
          turnstileToken: token,
          elapsed_ms: Date.now() - mountedAt.current,
        }),
      });

      const nextState = (await response.json()) as ContactState;
      setState(nextState);

      if (nextState.ok) {
        form.reset();
      } else {
        // Tokens are single-use; any failed attempt needs a fresh one.
        turnstileRef.current?.reset();
      }
    } catch {
      turnstileRef.current?.reset();
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
      <noscript>
        <p className="body-copy px-6 pt-8 sm:px-8">
          This form needs JavaScript. You can email us directly at{" "}
          <a href="mailto:contact@obsidura.com" className="underline">
            contact@obsidura.com
          </a>
          .
        </p>
      </noscript>
      <form
        onSubmit={handleSubmit}
        // Submitting needs JavaScript (Turnstile), and the noscript note above
        // points at email instead. action/method stay so a no-JS submit is
        // still a POST - without them the browser would GET the current page
        // with every field in the URL. The route answers it with a 415.
        action="/api/contact"
        method="post"
        // The API route returns field errors in the site's own voice;
        // without noValidate the browser's native bubbles fire first and
        // those errors are never reached. required stays on the fields for
        // its semantics - screen readers still announce the fields as such.
        noValidate
        className="relative flex flex-col gap-6 px-6 py-8 sm:px-8"
      >
        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <label htmlFor="name" className={labelClass}>
              Name
            </label>
            <Input
              id="name"
              name="name"
              type="text"
              required
              autoComplete="name"
              aria-invalid={state.fieldErrors?.name ? true : undefined}
              aria-describedby={
                state.fieldErrors?.name ? "name-error" : undefined
              }
              className={cn(
                fieldClass,
                state.fieldErrors?.name && "border-accent"
              )}
            />
            {state.fieldErrors?.name ? (
              <p
                id="name-error"
                className="mt-2 font-mono text-[12px] text-ink-mute"
              >
                {state.fieldErrors.name}
              </p>
            ) : null}
          </div>
          <div>
            <label htmlFor="email" className={labelClass}>
              Email
            </label>
            <Input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              aria-invalid={state.fieldErrors?.email ? true : undefined}
              aria-describedby={
                state.fieldErrors?.email ? "email-error" : undefined
              }
              className={cn(
                fieldClass,
                state.fieldErrors?.email && "border-accent"
              )}
            />
            {state.fieldErrors?.email ? (
              <p
                id="email-error"
                className="mt-2 font-mono text-[12px] text-ink-mute"
              >
                {state.fieldErrors.email}
              </p>
            ) : null}
          </div>
        </div>

        <div>
          <label htmlFor="company" className={labelClass}>
            Company <span className="text-ink-faint">(optional)</span>
          </label>
          <Input
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
          <Textarea
            id="message"
            name="message"
            required
            rows={6}
            aria-invalid={state.fieldErrors?.message ? true : undefined}
            aria-describedby={
              state.fieldErrors?.message ? "message-error" : undefined
            }
            className={cn(
              fieldClass,
              "resize-y min-h-[9rem]",
              state.fieldErrors?.message && "border-accent"
            )}
          />
          {state.fieldErrors?.message ? (
            <p
              id="message-error"
              className="mt-2 font-mono text-[12px] text-ink-mute"
            >
              {state.fieldErrors.message}
            </p>
          ) : null}
        </div>

        {/* Honeypot â€” hidden from humans */}
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

        <TurnstileWidget
          ref={turnstileRef}
          action="contact"
          onToken={setToken}
          onUnavailable={() => setVerifyUnavailable(true)}
        />

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
          <StatefulButton
            type="submit"
            pending={pending}
            className="kicker shrink-0 bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft disabled:cursor-wait disabled:opacity-60"
          >
            {pending ? "Sending..." : "Send message"}
          </StatefulButton>
        </div>
      </form>
    </FramePanel>
  );
}
