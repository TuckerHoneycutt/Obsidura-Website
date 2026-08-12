"use client";

import { useCallback, useEffect, useId, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { LogoMark } from "@/components/logo-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { scrollToSection } from "@/lib/scroll-to-section";

// The "Book a demo" button already carries people to /contact, so the centre
// row stays on the four homepage chapters rather than crowding in a fifth.
const SECTION_LINKS = [
  { label: "Reports", hash: "#reports" },
  { label: "Workflows", hash: "#definitions" },
  { label: "Runtime", hash: "#runtime" },
  { label: "Deploy", hash: "#deploy" },
] as const;

// The panel repeats the chapters and adds the pages that only the footer
// otherwise reaches, since a phone has no section rail to fall back on.
const PANEL_PAGES = [
  { label: "Platform", href: "/platform" },
  { label: "Integrations", href: "/integrations" },
  { label: "Security", href: "/security" },
  { label: "FAQ", href: "/faq" },
  { label: "Contact", href: "/contact" },
] as const;

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

  function onSectionClick(e: React.MouseEvent, hash: string) {
    // Already on the homepage: scroll in place. A soft nav to "/#runtime"
    // remounts the whole page and feels like lag.
    if (pathname === "/") {
      e.preventDefault();
      close();
      scrollToSection(hash);
    }
  }

  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className="sticky top-0 z-50 border-b border-rule bg-paper/85 backdrop-blur-sm"
    >
      <nav className="mx-auto grid max-w-6xl grid-cols-[1fr_auto] items-center gap-6 px-6 py-4 sm:grid-cols-[1fr_auto_1fr]">
        <Link href="/" className="group flex w-max items-center gap-2.5">
          <LogoMark size={26} />
          <span className="font-display text-xl leading-none font-medium tracking-[0.3em] uppercase">
            Obsidura
          </span>
        </Link>
        <div className="hidden items-center justify-center gap-8 sm:flex">
          {SECTION_LINKS.map((link) => (
            <Link
              key={link.hash}
              href={`/${link.hash}`}
              scroll={false}
              onClick={(e) => onSectionClick(e, link.hash)}
              className="link-sweep font-display text-[15px] font-medium tracking-[0.2em] text-ink-mute uppercase transition-colors hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
        </div>
        <div className="flex items-center justify-end gap-3">
          <ThemeToggle />
          {/* Below sm the hamburger takes this slot; the panel carries its
              own demo CTA, so nothing is lost. */}
          <Link
            href="/contact"
            className="font-display hidden border border-accent-deep px-3.5 py-2 text-sm font-medium tracking-[0.18em] text-accent uppercase transition-colors hover:bg-accent hover:text-paper sm:inline-block"
          >
            Book a demo
          </Link>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls={panelId}
            aria-label={open ? "Close menu" : "Open menu"}
            className="flex size-8 items-center justify-center border border-rule text-ink-mute transition-colors hover:border-accent-deep hover:text-ink sm:hidden"
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
            className="overflow-hidden border-t border-rule bg-paper sm:hidden"
          >
            <div className="px-6 py-6">
              <p className="kicker !text-[10px] text-accent">the homepage</p>
              <ul className="mt-3 space-y-1">
                {SECTION_LINKS.map((link) => (
                  <li key={link.hash}>
                    <Link
                      href={`/${link.hash}`}
                      scroll={false}
                      onClick={(e) => onSectionClick(e, link.hash)}
                      className="font-display block py-2 text-2xl font-light tracking-tight"
                    >
                      {link.label}
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
                Book a demo
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
