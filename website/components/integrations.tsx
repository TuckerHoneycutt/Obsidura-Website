import Link from "next/link";
import { BrandIcon } from "@/components/ui/brand-icons";
import {
  InfiniteMarquee,
  type MarqueeItem,
} from "@/components/ui/infinite-marquee";

// The services teams already work in, named the way they know them. REST
// APIs close the strip: the HTTP connector reaches anything that speaks one,
// local resources and internal databases included.
const INTEGRATIONS: MarqueeItem[] = [
  { label: "Google Workspace", icon: <BrandIcon name="google" /> },
  "Microsoft 365",
  "Microsoft Azure",
  "Slack",
  { label: "Jira", icon: <BrandIcon name="jira" /> },
  { label: "Confluence", icon: <BrandIcon name="confluence" /> },
  { label: "Linear", icon: <BrandIcon name="linear" /> },
  { label: "GitHub", icon: <BrandIcon name="github" /> },
  { label: "Notion", icon: <BrandIcon name="notion" /> },
  { label: "Postgres", icon: <BrandIcon name="postgres" /> },
  "S3-compatible storage",
  "NAS (SMB)",
  { label: "MCP servers", icon: <BrandIcon name="mcp" /> },
  "REST APIs",
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
        {/* The marquee stays shipped-only; the designed catalog gets a
            door, not a place in the list. */}
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
