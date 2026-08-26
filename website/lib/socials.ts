/**
 * Obsidura's social profiles - the handle is "obsidura" on every platform.
 * One list feeds the footer, the contact page, and the Organization
 * structured data's sameAs, so a new platform is added in exactly one place.
 */
export type Social = {
  label: string;
  handle: string;
  href: string;
};

export const SOCIALS: Social[] = [
  { label: "X", handle: "@obsidura", href: "https://x.com/obsidura" },
  {
    label: "LinkedIn",
    handle: "/obsidura",
    href: "https://www.linkedin.com/company/obsidura",
  },
  {
    label: "Instagram",
    handle: "@obsidura",
    href: "https://www.instagram.com/obsidura",
  },
  {
    label: "YouTube",
    handle: "@obsidura",
    href: "https://www.youtube.com/@obsidura",
  },
  {
    label: "TikTok",
    handle: "@obsidura",
    href: "https://www.tiktok.com/@obsidura",
  },
];
