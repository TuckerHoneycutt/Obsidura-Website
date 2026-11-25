"use client";

import { useCallback, useEffect, useId, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { LogoMark } from "@/components/logo-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { BOOKING_URL } from "@/lib/booking";
import { cn } from "@/lib/utils";

// The panel lists every other page the site has, plus the booking link.
// Contact is absent because the panel closes on it as its own CTA below.
const PANEL_PAGES = [
  { label: "Book a Demo", href: BOOKING_URL },
  { label: "Security", href: "/security" },
  { label: "FAQ", href: "/faq" },
  { label: "Privacy", href: "/privacy" },
] as const;

const barLinkClass =
  "link-sweep font-display text-[15px] font-medium tracking-[0.2em] uppercase transition-colors hover:text-ink";

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
      {/* The viewport frame's top rule crosses the header 12px down, so from
          md (where the frame exists) the top padding carries that 12px extra:
          the gap from the rule to the content then equals the gap from the
          content to the header's bottom border. */}
      {/* From lg the side columns share the leftover space equally, so the
          centered link column lands on the true center of the bar rather
          than the center of whatever the logo left over. */}
      <nav className="mx-auto grid max-w-6xl grid-cols-[1fr_auto] items-center gap-6 px-6 py-4 md:pt-7 sm:grid-cols-[auto_1fr_auto] lg:grid-cols-[1fr_auto_1fr]">
        <Link href="/" className="group flex w-max items-center gap-1.5">
          <LogoMark size={26} />
          <span className="font-display text-xl leading-none font-medium tracking-[0.3em] uppercase">
            Obsidura
          </span>
        </Link>
        {/* Nudged 2px down: link-sweep's 3px underline padding and the
            descender-free caps otherwise sit the words above the bar's
            optical center. */}
        <div className="hidden translate-y-[2px] items-center justify-center gap-8 lg:flex">
          <Link
            href="/contact"
            transitionTypes={["nav-forward"]}
            aria-current={pathname === "/contact" ? "page" : undefined}
            className={cn(
              barLinkClass,
              pathname === "/contact" ? "text-ink" : "text-ink-mute"
            )}
          >
            Contact
          </Link>
          {/* External, so a plain anchor rather than a routed Link. */}
          <a href={BOOKING_URL} className={cn(barLinkClass, "text-ink-mute")}>
            Book a Demo
          </a>
        </div>
        <div className="flex items-center justify-end gap-3">
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
            {/* Scrolls on its own (data-lenis-prevent, since Lenis owns the
                wheel even while stopped) so every entry stays reachable on
                short screens where the panel outgrows the viewport. */}
            <div
              data-lenis-prevent
              className="max-h-[calc(100dvh-6rem)] overflow-y-auto px-6 py-6"
            >
              <ul className="space-y-1">
                {PANEL_PAGES.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      onClick={close}
                      className="font-display block py-2 text-2xl font-light tracking-tight"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>

              <Link
                href="/contact"
                onClick={close}
                className="kicker mt-5 block bg-accent px-5 py-3.5 text-center !text-paper"
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
