import Link from "next/link";
import { CHAPTERS } from "@/lib/chapters";

/**
 * The 404, in the house voice: a page that does not exist is a lookup that
 * found nothing, so the page says so the way the run log would - a deny
 * line, then the chapters as the way back in. Static on purpose: no
 * reveals, no engraving chunk, nothing for a dead address to wait on.
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
            chapters below are the way back in.
          </p>

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

          <ol className="mt-14 border-t border-rule">
            {CHAPTERS.map((chapter) => (
              <li key={chapter.slug}>
                <Link
                  href={`/${chapter.slug}`}
                  transitionTypes={["nav-forward"]}
                  className="group flex items-baseline gap-6 border-b border-rule py-4 transition-colors hover:bg-paper-warm/50 sm:px-3"
                >
                  <span className="kicker w-8 shrink-0 text-accent">
                    {chapter.numeral}
                  </span>
                  <span className="font-display flex-1 text-xl font-light tracking-tight">
                    {chapter.label}
                  </span>
                  <span aria-hidden className="kicker shrink-0">
                    &rarr;
                  </span>
                </Link>
              </li>
            ))}
          </ol>

          <div className="mt-10 flex flex-wrap gap-x-8 gap-y-3">
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
