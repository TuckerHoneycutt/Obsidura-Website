import Image from "next/image";
import Link from "next/link";
import { LogoMark } from "@/components/logo-mark";
import { MeanderFrieze, MeanderMark } from "@/components/ui/meander-mark";
import { SOCIALS } from "@/lib/socials";

// The directory columns retired with the engine chapters; the bottom bar
// now carries every page the site still has.
const LINKS = [
  { label: "Security", href: "/security" },
  { label: "FAQ", href: "/faq" },
  { label: "Privacy", href: "/privacy" },
  { label: "Contact", href: "/contact" },
];

export function Footer() {
  return (
    <footer className="relative mt-auto overflow-hidden border-t border-rule">
      {/* Temple frieze: running key just below the top rule, running the
          width of the page in whole units. The padding matches the viewport
          frame's inset-3, so the band stops at its vertical rules rather
          than running beneath them. */}
      <div className="md:px-3">
        <MeanderFrieze className="mt-4 opacity-70" />
      </div>
      {/* Full-contrast lockup: mark and wordmark proportioned per the brand
          lockup, where the mark stands roughly twice the wordmark cap height */}
      <div className="mx-auto mt-10 flex max-w-6xl items-center justify-center gap-[clamp(0.625rem,1.75vw,1.375rem)] px-5">
        <Image
          src="/logo-mark.svg"
          alt=""
          width={718}
          height={718}
          unoptimized
          className="logo-invert h-[clamp(3.5rem,12vw,10.25rem)] w-auto select-none"
        />
        <p className="font-display text-[clamp(2.75rem,9.5vw,8rem)] leading-none font-light tracking-[0.1em] uppercase">
          Obsidura
        </p>
      </div>
      <div className="relative mx-auto mt-10 flex max-w-6xl items-center justify-center gap-2.5 px-5 text-ink-mute">
        <MeanderMark size={10} />
        <p className="kicker !text-[10px]">forged on pantheon</p>
        <MeanderMark size={10} />
      </div>
      {/* The profiles run as one strip in the dress of the "forged on
          pantheon" line - external links read better as a band than as a
          column towering over the directory. Plain anchors, since they
          leave the site. */}
      <div className="relative mx-auto mt-12 flex max-w-6xl flex-wrap items-center justify-center gap-x-7 gap-y-3 border-t border-rule px-5 py-7 text-ink-mute">
        <MeanderMark size={10} className="text-ink-faint" />
        {SOCIALS.map(({ label, href }) => (
          <a
            key={href}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="kicker link-sweep !text-[10px] transition-colors hover:text-ink"
          >
            {label}
          </a>
        ))}
        <MeanderMark size={10} className="text-ink-faint" />
      </div>
      <div className="relative mx-auto flex max-w-6xl flex-col gap-5 border-t border-rule px-5 py-9 sm:flex-row sm:items-center sm:justify-between">
        <p className="kicker flex items-center gap-2.5">
          <LogoMark size={16} />
          &copy; 2026 Obsidura
        </p>
        <div className="flex flex-wrap gap-6">
          {LINKS.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="kicker link-sweep transition-colors hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </footer>
  );
}
