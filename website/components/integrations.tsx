import Link from "next/link";
import { InfiniteMarquee } from "@/components/ui/infinite-marquee";

const INTEGRATIONS = [
  "Postgres",
  "Object storage",
  "HTTP services",
  "Row-filter scope",
  "Key-prefix scope",
  "URL allowlist",
  "Run-scoped proxy",
  "Audited per call",
];

export function Integrations() {
  return (
    <section className="border-t border-rule">
      <div className="mx-auto flex max-w-6xl flex-col gap-5 px-5 py-10 sm:flex-row sm:items-center sm:gap-10">
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
