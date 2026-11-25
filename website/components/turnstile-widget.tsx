"use client";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import Script from "next/script";
import { useTheme } from "next-themes";

// Minimal typing for the parts of the Turnstile API used here.
// https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/
type TurnstileApi = {
  render: (
    el: HTMLElement,
    options: {
      sitekey: string;
      action?: string;
      theme?: "light" | "dark" | "auto";
      size?: "normal" | "flexible" | "compact";
      callback?: (token: string) => void;
      "expired-callback"?: () => void;
      "error-callback"?: () => void;
    }
  ) => string;
  reset: (id: string) => void;
  remove: (id: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

export type TurnstileHandle = { reset: () => void };

const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
const SCRIPT_SRC =
  "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

export function TurnstileWidget({
  action,
  onToken,
  onUnavailable,
  ref,
}: {
  action: string;
  // Called with a fresh token, or "" when the current one expires or errors.
  onToken: (token: string) => void;
  // The script failed to load (blocked, offline) or no site key is set.
  onUnavailable: () => void;
  ref?: Ref<TurnstileHandle>;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const [ready, setReady] = useState(false);
  const { resolvedTheme } = useTheme();

  // Latest callbacks without re-rendering the widget when they change.
  const onTokenRef = useRef(onToken);
  const onUnavailableRef = useRef(onUnavailable);
  useEffect(() => {
    onTokenRef.current = onToken;
    onUnavailableRef.current = onUnavailable;
  });

  useImperativeHandle(ref, () => ({
    reset() {
      onTokenRef.current("");
      if (widgetId.current && window.turnstile) {
        window.turnstile.reset(widgetId.current);
      }
    },
  }));

  useEffect(() => {
    if (!SITE_KEY) {
      console.error("NEXT_PUBLIC_TURNSTILE_SITE_KEY is not set");
      onUnavailableRef.current();
    }
  }, []);

  // (Re)render when the script is ready and whenever the theme flips; the
  // widget has no API for changing theme in place.
  useEffect(() => {
    const el = containerRef.current;
    const api = window.turnstile;
    if (!ready || !SITE_KEY || !el || !api) return;

    const id = api.render(el, {
      sitekey: SITE_KEY,
      action,
      theme: resolvedTheme === "dark" ? "dark" : "light",
      size: "flexible",
      callback: (token) => onTokenRef.current(token),
      "expired-callback": () => onTokenRef.current(""),
      "error-callback": () => onTokenRef.current(""),
    });
    widgetId.current = id;

    return () => {
      api.remove(id);
      widgetId.current = null;
      onTokenRef.current("");
    };
  }, [ready, action, resolvedTheme]);

  if (!SITE_KEY) return null;

  return (
    <>
      <Script
        src={SCRIPT_SRC}
        // onReady fires on first load and again on every remount, e.g.
        // navigating away from /contact and back.
        onReady={() => setReady(true)}
        onError={() => onUnavailableRef.current()}
      />
      <div ref={containerRef} className="min-h-[65px]" />
    </>
  );
}
