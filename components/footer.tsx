import Image from "next/image";
import { LogoMark } from "@/components/logo-mark";

const LINKS = [
  { label: "FAQ", href: "#" },
  { label: "Docs", href: "#" },
  { label: "Privacy", href: "#" },
  { label: "Partner with us", href: "mailto:hello@obsidura.com" },
];

export function Footer() {
  return (
    <footer className="mt-auto border-t border-rule">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 px-5 pt-12">
        <Image
          src="/logo-lockup-alpha.png"
          alt="Obsidura"
          width={340}
          height={100}
          className="logo-invert h-16 w-auto select-none opacity-80 sm:h-20"
        />
        <p className="kicker !text-[10px]">grown on yggdrasil</p>
      </div>
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 sm:flex-row sm:items-center sm:justify-between">
        <p className="kicker flex items-center gap-2.5">
          <LogoMark size={16} />
          &copy; 2026 Obsidura
        </p>
        <div className="flex flex-wrap gap-6">
          {LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="kicker transition-colors hover:text-ink"
            >
              {link.label}
            </a>
          ))}
        </div>
      </div>
    </footer>
  );
}
