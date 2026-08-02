import Image from "next/image";
import Link from "next/link";
import { LogoMark } from "@/components/logo-mark";
import { MeanderFrieze, MeanderMark } from "@/components/ui/meander-mark";

const DIRECTORY: { heading: string; links: { label: string; href: string }[] }[] = [
  {
    heading: "platform",
    links: [
      { label: "Architecture", href: "/platform" },
      { label: "Integrations", href: "/integrations" },
      { label: "Security", href: "/security" },
      { label: "FAQ", href: "/faq" },
    ],
  },
  {
    heading: "solutions",
    links: [
      { label: "Finance Operations", href: "/solutions/finance-operations" },
      { label: "Customer Support", href: "/solutions/customer-support" },
      { label: "Revenue Operations", href: "/solutions/revenue-operations" },
    ],
  },
  {
    heading: "deployment",
    links: [
      { label: "Obsidura Cloud", href: "/deployment/cloud" },
      { label: "Private VPC", href: "/deployment/private-vpc" },
      { label: "On-Premises", href: "/deployment/on-premises" },
    ],
  },
  {
    heading: "company",
    links: [
      { label: "Contact", href: "/contact" },
      { label: "Privacy", href: "/privacy" },
    ],
  },
];

const LINKS = [
  { label: "FAQ", href: "/faq" },
  { label: "Security", href: "/security" },
  { label: "Privacy", href: "/privacy" },
  { label: "Contact", href: "/contact" },
];

export function Footer() {
  return (
    <footer className="relative mt-auto overflow-hidden border-t border-rule">
      {/* Temple frieze: running key just below the top rule, aligned to the
          same content column as the rest of the footer */}
      <div className="mx-auto max-w-6xl px-5">
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
      <div className="relative mx-auto mt-12 grid max-w-6xl grid-cols-2 gap-x-6 gap-y-10 border-t border-rule px-5 py-10 sm:grid-cols-4">
        {DIRECTORY.map(({ heading, links }) => (
          <div key={heading}>
            <p className="kicker mb-4 !text-[10px] text-accent">{heading}</p>
            <ul className="space-y-2.5">
              {links.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="kicker link-sweep transition-colors hover:text-ink"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
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
