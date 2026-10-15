import Link from "next/link";
import { TextHoverEffect } from "@/components/ui/text-hover-effect";

/**
 * The 404, in the house voice: a page that does not exist is a lookup that
 * found nothing, so the page says so the way the run log would - a deny
 * line, then the way back in. No reveals and nothing fetched; the one
 * flourish is the outlined numerals, which need no data to draw.
 */
export default function NotFound() {
  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <section className="relative">
        <div className="mx-auto max-w-3xl px-5 pt-16 pb-20 lg:pt-24 lg:pb-28">
          <p className="kicker mb-6 text-accent">nothing recorded here</p>
          <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
            No such <span className="headline-emph">page.</span>
          </h1>
          <p className="lede-copy mt-6 max-w-xl">
            The address may be mistyped, or the page may have moved. The
            beginning is the way back in.
          </p>

          {/* Oversized outlined numerals that trace themselves on and glow
              under the pointer. Decorative: the heading above says it. */}
          <div className="mt-8 -mb-4 h-40 sm:h-56">
            <TextHoverEffect text="404" duration={0.2} />
          </div>

          <div className="mt-10 border border-rule bg-paper-warm/40 px-4 py-3">
            <p className="flex flex-wrap gap-x-3 font-mono text-[12.5px] leading-relaxed">
              <span className="text-ink-faint">[404]</span>
              <span className="uppercase tracking-wider text-ink underline underline-offset-4">
                deny
              </span>
              <span className="text-ink-soft">
                get &middot; this address &middot; no page registered &mdash;
                decision written to the log
              </span>
            </p>
          </div>

          <div className="mt-14 flex flex-wrap gap-x-8 gap-y-3">
            <Link
              href="/"
              transitionTypes={["nav-back"]}
              className="kicker link-sweep text-accent transition-colors hover:text-ink"
            >
              &larr; back to the beginning
            </Link>
            <Link
              href="/contact"
              className="kicker link-sweep transition-colors hover:text-ink"
            >
              report a missing page &rarr;
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
