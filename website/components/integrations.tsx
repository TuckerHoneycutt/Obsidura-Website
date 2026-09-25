import Link from "next/link";
import { BrandIcon } from "@/components/ui/brand-icons";
import {
  InfiniteMarquee,
  type MarqueeItem,
} from "@/components/ui/infinite-marquee";

// Shipped connectors lead, in full ink: Postgres, object storage, and the
// HTTP connector that reaches anything with an API. The named services
// after them are the designed v1 catalog and say so - the /integrations
// page is plain that they are not in the engine yet, and the strip must
// not claim more than that page does.
const INTEGRATIONS: MarqueeItem[] = [
  { label: "Postgres", icon: <BrandIcon name="postgres" /> },
  "S3-compatible storage",
  "REST APIs",
  { label: "Google Workspace", icon: <BrandIcon name="google" />, note: "planned" },
  { label: "Microsoft 365", note: "planned" },
  { label: "Slack", note: "planned" },
  { label: "Jira", icon: <BrandIcon name="jira" />, note: "planned" },
  { label: "Microsoft Azure", note: "planned" },
  { label: "NAS (SMB)", note: "planned" },
  { label: "MCP servers", icon: <BrandIcon name="mcp" />, note: "planned" },
];

export function Integrations() {
  return (
    <section className="border-t border-rule">
      <div className="mx-auto flex max-w-shell flex-col gap-5 px-gutter py-10 sm:flex-row sm:items-center sm:gap-10 xl:gap-14">
        <Link
          href="/integrations"
          className="kicker link-sweep shrink-0 transition-colors hover:text-ink"
        >
          Integrations
        </Link>
        <InfiniteMarquee items={INTEGRATIONS} className="flex-1" />
        {/* Planned entries are tagged in the strip; the full designed
            catalog, with the phase each one ships in, is behind this door. */}
        <Link
          href="/connections"
          className="kicker link-sweep shrink-0 text-ink-mute transition-colors hover:text-ink"
        >
          the v1 catalog &rarr;
        </Link>
      </div>
    </section>
  );
}
