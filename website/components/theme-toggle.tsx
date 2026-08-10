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

function applyThemeClass(next: "light" | "dark") {
  const root = document.documentElement;
  root.classList.remove("light", "dark");
  root.classList.add(next);
}

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();

  function toggleTheme() {
    const next = resolvedTheme === "dark" ? "light" : "dark";
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    const apply = () => {
      // Flip the class synchronously so View Transitions (and instant
      // toggles) see the new palette in the same frame as the click.
      applyThemeClass(next);
      setTheme(next);
    };

    if (
      !reduceMotion &&
      typeof document.startViewTransition === "function"
    ) {
      document.startViewTransition(apply);
      return;
    }

    apply();
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
