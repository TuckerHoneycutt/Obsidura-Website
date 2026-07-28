import Image from "next/image";
import { LogoMark } from "@/components/logo-mark";
import { RuneMark } from "@/components/ui/rune-mark";

const LINKS = [
  { label: "FAQ", href: "#" },
  { label: "Docs", href: "#" },
  { label: "Privacy", href: "#" },
  { label: "Partner with us", href: "mailto:hello@obsidura.com" },
];

export function Footer() {
  return (
    <footer className="relative mt-auto overflow-hidden border-t border-rule pt-14">
      {/* Full-contrast lockup: mark and wordmark proportioned per the brand
          lockup, where the mark stands roughly twice the wordmark cap height */}
      <div className="mx-auto flex max-w-6xl items-center justify-center gap-[clamp(0.625rem,1.75vw,1.375rem)] px-5">
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
        <RuneMark size={10} />
        <p className="kicker !text-[10px]">grown on yggdrasil</p>
        <RuneMark size={10} />
      </div>
      <div className="relative mx-auto mt-12 flex max-w-6xl flex-col gap-5 border-t border-rule px-5 py-9 sm:flex-row sm:items-center sm:justify-between">
        <p className="kicker flex items-center gap-2.5">
          <LogoMark size={16} />
          &copy; 2026 Obsidura
        </p>
        <div className="flex flex-wrap gap-6">
          {LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="kicker link-sweep transition-colors hover:text-ink"
            >
              {link.label}
            </a>
          ))}
        </div>
      </div>
    </footer>
  );
}
