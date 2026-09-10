"use client";

import { useEffect } from "react";
import Link from "next/link";

/**
 * The error boundary, in the same voice as the run log: a failed render is
 * a failed run, and a failed run is stated plainly, recorded, and offered a
 * retry. The digest is the identifier the server logs carry, so showing it
 * gives a reader something concrete to report.
 */
export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main id="content" tabIndex={-1} className="flex-1">
      <section className="relative">
        <div className="mx-auto max-w-3xl px-5 pt-16 pb-20 lg:pt-24 lg:pb-28">
          <p className="kicker mb-6 text-accent">the page failed</p>
          <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
            Something broke <span className="headline-emph">mid-run.</span>
          </h1>
          <p className="lede-copy mt-6 max-w-xl">
            The failure is recorded. Retry the page; if it fails again, send
            word through the contact page.
          </p>

          {error.digest ? (
            <div className="mt-10 border border-rule bg-paper-warm/40 px-4 py-3">
              <p className="flex flex-wrap gap-x-3 font-mono text-[12.5px] leading-relaxed">
                <span className="text-ink-faint">[error]</span>
                <span className="uppercase tracking-wider text-ink-mute">
                  digest
                </span>
                <span className="text-ink-soft">{error.digest}</span>
              </p>
            </div>
          ) : null}

          <div className="mt-10 flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={() => unstable_retry()}
              className="kicker inline-block bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
            >
              Try again
            </button>
            <Link
              href="/"
              className="kicker inline-block border border-accent-deep bg-paper px-6 py-3.5 !text-ink transition-colors hover:border-accent"
            >
              back to the beginning
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
