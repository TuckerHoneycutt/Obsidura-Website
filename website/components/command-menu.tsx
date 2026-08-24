"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Command } from "cmdk";
import { CHAPTERS } from "@/lib/chapters";
import { MeanderMark } from "@/components/ui/meander-mark";

// Every destination the footer knows, grouped the way the footer groups
// them - the palette is the same directory made reachable by keyboard.
const ELSEWHERE = [
  { label: "Integrations", href: "/integrations" },
  { label: "Connections", href: "/connections" },
  { label: "Security", href: "/security" },
  { label: "FAQ", href: "/faq" },
  { label: "Contact", href: "/contact" },
  { label: "Privacy", href: "/privacy" },
];

const EXAMPLES = [
  { label: "Financial Audit", href: "/solutions/financial-audit" },
  { label: "Flight Diagnostics", href: "/solutions/flight-diagnostics" },
  { label: "Clinical Summaries", href: "/solutions/clinical-summary" },
];

const DOMINIONS = [
  { label: "Obsidura Cloud", href: "/deployment/cloud" },
  { label: "Private VPC", href: "/deployment/private-vpc" },
  { label: "On-Premises", href: "/deployment/on-premises" },
];

const label = (slug: string) => slug.charAt(0).toUpperCase() + slug.slice(1);

function Heading({ children }: { children: ReactNode }) {
  return <span className="kicker !text-[10px] text-accent">{children}</span>;
}

function Item({
  onSelect,
  keywords,
  value,
  children,
}: {
  onSelect: () => void;
  keywords?: string[];
  value: string;
  children: ReactNode;
}) {
  return (
    <Command.Item
      value={value}
      keywords={keywords}
      onSelect={onSelect}
      className="font-display flex cursor-pointer items-center justify-between gap-4 px-3 py-2.5 text-lg font-light tracking-tight text-ink-soft data-[selected=true]:bg-paper-warm data-[selected=true]:text-ink"
    >
      {children}
    </Command.Item>
  );
}

/**
 * The site's directory behind one keystroke. The product's pitch is work
 * asked for in a sentence; ⌘K is that gesture applied to the site itself.
 * Opens on ⌘K / Ctrl+K, or on the event the nav button dispatches.
 */
export function CommandMenu() {
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    const onOpen = () => setOpen(true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("pantheon:command-menu", onOpen);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("pantheon:command-menu", onOpen);
    };
  }, []);

  // Route changes dismiss the palette during render, same as the nav panel.
  const [routeAtOpen, setRouteAtOpen] = useState(pathname);
  if (routeAtOpen !== pathname) {
    setRouteAtOpen(pathname);
    setOpen(false);
  }

  // Radix locks body scroll, but Lenis drives the page itself and has to
  // be paused explicitly - same dance the mobile nav panel does.
  useEffect(() => {
    if (!open) return;
    const lenis = window.__lenis;
    lenis?.stop?.();
    return () => lenis?.start?.();
  }, [open]);

  const go = useCallback(
    (href: string) => {
      setOpen(false);
      router.push(href, { transitionTypes: ["nav-forward"] });
    },
    [router]
  );

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Go to a page"
      overlayClassName="cmd-overlay fixed inset-0 z-[95] bg-paper/70 backdrop-blur-sm"
      contentClassName="cmd-panel fixed inset-x-5 top-[16vh] z-[96] mx-auto max-w-xl border border-rule bg-paper"
    >
      <div className="flex items-center gap-3 border-b border-rule px-4">
        <MeanderMark size={10} className="shrink-0 text-ink-faint" />
        <Command.Input
          placeholder="Name the page you want&hellip;"
          className="w-full bg-transparent py-3.5 font-mono text-sm text-ink outline-none placeholder:text-ink-faint"
        />
        <kbd className="kicker shrink-0 !text-[10px] text-ink-faint">esc</kbd>
      </div>
      {/* data-lenis-prevent: Lenis owns the wheel even while stopped, and
          without it the list swallows scroll and the lower groups are
          unreachable by mouse. */}
      <Command.List data-lenis-prevent className="max-h-[55vh] overflow-y-auto p-2">
        <Command.Empty className="px-3 py-6 font-mono text-[12px] text-ink-mute">
          Nothing by that name. The footer carries the full directory.
        </Command.Empty>

        <Command.Group heading={<Heading>the account</Heading>} className="p-1">
          {CHAPTERS.map((c) => (
            <Item
              key={c.slug}
              value={label(c.slug)}
              keywords={[c.name]}
              onSelect={() => go(`/${c.slug}`)}
            >
              <span className="flex items-baseline gap-3">
                <span className="kicker w-6 shrink-0 text-accent">
                  {c.numeral}
                </span>
                {label(c.slug)}
              </span>
              <span className="kicker !text-[10px] text-ink-faint">
                {c.name}
              </span>
            </Item>
          ))}
        </Command.Group>

        <Command.Group
          heading={<Heading>worked examples</Heading>}
          className="border-t border-rule p-1 pt-2"
        >
          {EXAMPLES.map((p) => (
            <Item key={p.href} value={p.label} onSelect={() => go(p.href)}>
              {p.label}
            </Item>
          ))}
        </Command.Group>

        <Command.Group
          heading={<Heading>deployment</Heading>}
          className="border-t border-rule p-1 pt-2"
        >
          {DOMINIONS.map((p) => (
            <Item key={p.href} value={p.label} onSelect={() => go(p.href)}>
              {p.label}
            </Item>
          ))}
        </Command.Group>

        <Command.Group
          heading={<Heading>elsewhere</Heading>}
          className="border-t border-rule p-1 pt-2"
        >
          {ELSEWHERE.map((p) => (
            <Item key={p.href} value={p.label} onSelect={() => go(p.href)}>
              {p.label}
            </Item>
          ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
