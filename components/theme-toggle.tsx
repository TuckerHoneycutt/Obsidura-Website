"use client";

import { useTheme } from "next-themes";

function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      className="size-3.5"
      aria-hidden
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-3.5"
      aria-hidden
    >
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

// Timer for removing the fade class; re-toggling mid-fade just extends
// the window instead of stacking classes.
let fadeTimer: number | undefined;

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();

  function toggleTheme() {
    const next = resolvedTheme === "dark" ? "light" : "dark";
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    if (reduceMotion) {
      setTheme(next);
      return;
    }

    // While .theme-fade is present, every element eases its colors along
    // the same curve (see globals.css), so the palette dissolves in one
    // uniform motion - no snapshots, nothing that can be torn down early.
    const html = document.documentElement;
    html.classList.add("theme-fade");
    setTheme(next);

    // Comfortably after the 380ms transitions: removing the class while
    // colors are still moving would snap them to their final values.
    window.clearTimeout(fadeTimer);
    fadeTimer = window.setTimeout(() => {
      html.classList.remove("theme-fade");
    }, 600);
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label="Toggle theme"
      className="flex size-8 items-center justify-center border border-rule text-ink-mute transition-colors hover:border-accent-deep hover:text-ink"
    >
      {/* Both icons render; the active theme picks one via CSS, so the
          markup stays identical between server and client. */}
      <span className="light:hidden">
        <MoonIcon />
      </span>
      <span className="hidden light:block">
        <SunIcon />
      </span>
    </button>
  );
}
