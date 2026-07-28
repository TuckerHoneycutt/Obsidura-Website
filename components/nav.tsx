"use client";

import { motion } from "motion/react";
import { LogoMark } from "@/components/logo-mark";
import { ThemeToggle } from "@/components/theme-toggle";

const LINKS = [
  { label: "Platform", href: "#platform" },
  { label: "Runtime", href: "#runtime" },
  { label: "Deploy", href: "#deploy" },
];

export function Nav() {
  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className="sticky top-0 z-50 border-b border-rule bg-paper/85 backdrop-blur-sm"
    >
      <nav className="mx-auto grid max-w-6xl grid-cols-[1fr_auto] items-center gap-6 px-6 py-4 sm:grid-cols-[1fr_auto_1fr]">
        <a href="#top" className="group flex w-max items-center gap-2.5">
          <motion.span
            className="inline-flex"
            whileHover={{ rotate: 180 }}
            transition={{ duration: 0.8, ease: [0.21, 0.47, 0.32, 0.98] }}
          >
            <LogoMark size={26} />
          </motion.span>
          <span className="font-display text-xl leading-none font-medium tracking-[0.3em] uppercase">
            Obsidura
          </span>
        </a>
        <div className="hidden items-center justify-center gap-10 sm:flex">
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="link-sweep font-display text-[15px] font-medium tracking-[0.2em] text-ink-mute uppercase transition-colors hover:text-ink"
            >
              {link.label}
            </a>
          ))}
        </div>
        <div className="flex items-center justify-end gap-3">
          <ThemeToggle />
          <a
            href="#deploy"
            className="font-display border border-accent-deep px-3.5 py-2 text-sm font-medium tracking-[0.18em] text-accent uppercase transition-colors hover:bg-accent hover:text-paper"
          >
            Book a demo
          </a>
        </div>
      </nav>
    </motion.header>
  );
}
