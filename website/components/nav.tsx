"use client";

import { useCallback, useEffect, useId, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { LogoMark } from "@/components/logo-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { CHAPTERS } from "@/lib/chapters";
import { cn } from "@/lib/utils";

// Four of the five chapters fit the centre row; governance reads as part of
// the same account and stays reachable from the index, the pager, and the
// mobile panel below.
const NAV_CHAPTERS = ["automations", "workflows", "runtime", "deploy"];

const navChapters = CHAPTERS.filter((c) => NAV_CHAPTERS.includes(c.slug));

// The panel lists every chapter, then the pages that only the footer
// otherwise reaches. Contact is absent because the panel closes on it
// as its own CTA below.
const PANEL_PAGES = [
  { label: "Integrations", href: "/integrations" },
  { label: "Security", href: "/security" },
  { label: "FAQ", href: "/faq" },
] as const;

/** Chapter titles double as their nav labels, capitalised from the slug. */
function label(slug: string) {
  return slug.charAt(0).toUpperCase() + slug.slice(1);
}

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={13}
      height={13}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="square"
      aria-hidden
      className={cn("shrink-0", className)}
    >
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </svg>
  );
}

/** Opens the command palette mounted in the layout; the event keeps the
    two components uncoupled. */
const openSearch = () =>
  window.dispatchEvent(new Event("pantheon:command-menu"));

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="square"
      className="size-4"
      aria-hidden
    >
      {open ? (
        <path d="M5 5l14 14M19 5L5 19" />
      ) : (
        <path d="M3 7h18M3 12h18M3 17h18" />
      )}
    </svg>
  );
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const panelId = useId();

  const close = useCallback(() => setOpen(false), []);

  // Route changes dismiss the panel, or it would hang open over the page it
  // just navigated to. Adjusted during render rather than in an effect, so
  // the panel is already gone in the same commit as the new route.
  const [routeAtOpen, setRouteAtOpen] = useState(pathname);
  if (routeAtOpen !== pathname) {
    setRouteAtOpen(pathname);
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);

    // Lenis drives the page itself, so it has to be paused explicitly -
    // overflow:hidden on the body does not reach it.
    const lenis = window.__lenis;
    lenis?.stop?.();
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      lenis?.start?.();
    };
  }, [open, close]);

  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      // Named so the directional slide leaves it alone: the header is the
      // fixed point that tells you the page moved, not the viewport.
      style={{ viewTransitionName: "site-header" }}
      className="sticky top-0 z-50 border-b border-rule bg-paper/85 backdrop-blur-sm"
    >
      {/* Auto side columns rather than equal thirds: the search bar made
          the right cluster wider than the left, and equal tracks squeezed
          it into wrapping. The links sit centred in the leftover space. */}
      {/* The viewport frame's top rule crosses the header 12px down, so from
          md (where the frame exists) the top padding carries that 12px extra:
          the gap from the rule to the content then equals the gap from the
          content to the header's bottom border. */}
      <nav className="mx-auto grid max-w-6xl grid-cols-[1fr_auto] items-center gap-6 px-6 py-4 md:pt-7 sm:grid-cols-[auto_1fr_auto]">
        <Link href="/" className="group flex w-max items-center gap-2.5">
          <LogoMark size={26} />
          <span className="font-display text-xl leading-none font-medium tracking-[0.3em] uppercase">
            Obsidura
          </span>
        </Link>
        <div className="hidden items-center justify-center gap-8 lg:flex">
          {/* Contact rides the same row as the chapters - it replaced the
              demo button, which pointed at the same page. */}
          {[...navChapters.map((c) => c.slug), "contact"].map((slug) => {
            const href = `/${slug}`;
            const current = pathname === href;
            return (
              <Link
                key={slug}
                href={href}
                transitionTypes={["nav-forward"]}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "link-sweep font-display text-[15px] font-medium tracking-[0.2em] uppercase transition-colors hover:text-ink",
                  current ? "text-ink" : "text-ink-mute"
                )}
              >
                {label(slug)}
              </Link>
            );
          })}
        </div>
        <div className="flex items-center justify-end gap-3">
          {/* A search field to look at, the command palette to use: the
              full bar where the row has room, an icon where it does not. */}
          <button
            type="button"
            onClick={openSearch}
            className="group hidden h-8 w-44 items-center gap-2.5 border border-rule px-3 text-left transition-colors hover:border-accent-deep xl:flex"
          >
            <SearchIcon className="text-ink-faint transition-colors group-hover:text-ink" />
            <span className="kicker !text-[10px] text-ink-faint transition-colors group-hover:text-ink">
              search
            </span>
            <kbd className="ml-auto font-mono text-[10px] text-ink-faint">
              &#8984;K
            </kbd>
          </button>
          <button
            type="button"
            onClick={openSearch}
            aria-label="Search the site"
            className="hidden size-8 items-center justify-center border border-rule text-ink-mute transition-colors hover:border-accent-deep hover:text-ink lg:flex xl:hidden"
          >
            <SearchIcon />
          </button>
          <ThemeToggle />
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls={panelId}
            aria-label={open ? "Close menu" : "Open menu"}
            className="flex size-8 items-center justify-center border border-rule text-ink-mute transition-colors hover:border-accent-deep hover:text-ink lg:hidden"
          >
            <MenuIcon open={open} />
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {open && (
          <motion.div
            id={panelId}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.28, ease: [0.21, 0.47, 0.32, 0.98] }}
            className="overflow-hidden border-t border-rule bg-paper lg:hidden"
          >
            <div className="px-6 py-6">
              <button
                type="button"
                onClick={() => {
                  close();
                  openSearch();
                }}
                className="mb-6 flex h-10 w-full items-center gap-2.5 border border-rule px-3 text-left"
              >
                <SearchIcon className="text-ink-faint" />
                <span className="kicker !text-[10px] text-ink-mute">
                  search the site
                </span>
              </button>
              <p className="kicker !text-[10px] text-accent">the account</p>
              <ul className="mt-3 space-y-1">
                {CHAPTERS.map((chapter) => (
                  <li key={chapter.slug}>
                    <Link
                      href={`/${chapter.slug}`}
                      transitionTypes={["nav-forward"]}
                      onClick={close}
                      className="font-display flex items-baseline gap-3 py-2 text-2xl font-light tracking-tight"
                    >
                      <span className="kicker w-6 shrink-0 text-accent">
                        {chapter.numeral}
                      </span>
                      {label(chapter.slug)}
                    </Link>
                  </li>
                ))}
              </ul>

              <p className="kicker mt-6 border-t border-rule pt-5 !text-[10px] text-accent">
                elsewhere
              </p>
              <ul className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1">
                {PANEL_PAGES.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      onClick={close}
                      className="font-display block py-2 text-lg font-light tracking-tight text-ink-soft"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>

              <Link
                href="/contact"
                onClick={close}
                className="kicker mt-6 block bg-accent px-5 py-3.5 text-center !text-paper"
              >
                Contact
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
