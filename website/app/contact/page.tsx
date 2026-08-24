import type { Metadata } from "next";
import Link from "next/link";
import { ContactForm } from "@/components/contact-form";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderMark } from "@/components/ui/meander-mark";

export const metadata: Metadata = {
  title: "Contact - Obsidura",
  description:
    "Get in touch with Obsidura — book a demo, ask about deployment, or send word to the company.",
  alternates: {
    canonical: "/contact",
  },
};

export default function ContactPage() {
  return (
    <main className="flex-1">
      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 pt-16 pb-20 lg:grid-cols-[1fr_1.15fr] lg:gap-16 lg:pt-24 lg:pb-28">
          <div>
            <p className="kicker mb-6 text-accent">v &mdash; send word</p>
            <h1 className="font-display text-[clamp(2.75rem,6vw,4.5rem)] leading-[1.02] font-light tracking-tight">
              Tell us what you are{" "}
              <span className="headline-emph">trying to run.</span>
            </h1>
            <p className="lede-copy mt-7 max-w-md">
              Design partners, deployment questions, or a thirty-minute demo
              — send word and we will see it carried to the right person.
            </p>

            <div className="mt-10 space-y-4">
              <FramePanel className="inline-block bg-paper-warm/40 px-4 py-3">
                <p className="kicker flex items-center gap-2.5">
                  <MeanderMark size={10} />
                  <a
                    href="mailto:contact@obsidura.com"
                    className="link-sweep transition-colors hover:text-ink"
                  >
                    contact@obsidura.com
                  </a>
                </p>
              </FramePanel>
              <p className="font-mono text-[12px] leading-relaxed text-ink-mute">
                Prefer email directly? That address lands in the same inbox.
              </p>
              <p className="font-mono text-[12px] leading-relaxed text-ink-mute">
                Rather write to a person? The officers are listed on the{" "}
                <Link
                  href="/about"
                  className="link-sweep text-ink-soft transition-colors hover:text-ink"
                >
                  about page
                </Link>
                .
              </p>
            </div>
          </div>

          <ContactForm />
        </div>
      </section>
    </main>
  );
}
