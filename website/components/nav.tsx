"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { LogoMark } from "@/components/logo-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { scrollToSection } from "@/lib/scroll-to-section";

const SECTION_LINKS = [
  { label: "Platform", hash: "#platform" },
  { label: "Runtime", hash: "#runtime" },
  { label: "Deploy", hash: "#deploy" },
] as const;

const PAGE_LINKS = [{ label: "Contact", href: "/contact" }] as const;

export function Nav() {
  const pathname = usePathname();

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
              onClick={(e) => {
                // Already on the homepage: scroll in place. A soft nav to
                // "/#runtime" remounts the whole page and feels like lag.
                if (pathname === "/") {
                  e.preventDefault();
                  scrollToSection(link.hash);
                }
              }}
              className="link-sweep font-display text-[15px] font-medium tracking-[0.2em] text-ink-mute uppercase transition-colors hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
          {PAGE_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="link-sweep font-display text-[15px] font-medium tracking-[0.2em] text-ink-mute uppercase transition-colors hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
        </div>
        <div className="flex items-center justify-end gap-3">
          <ThemeToggle />
          <Link
            href="/contact"
            className="font-display border border-accent-deep px-3.5 py-2 text-sm font-medium tracking-[0.18em] text-accent uppercase transition-colors hover:bg-accent hover:text-paper"
          >
            Book a demo
          </Link>
        </div>
      </nav>
    </motion.header>
  );
}
