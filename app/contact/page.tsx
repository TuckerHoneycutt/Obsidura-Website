import type { Metadata } from "next";
import { Nav } from "@/components/nav";
import { Footer } from "@/components/footer";
import { ContactForm } from "@/components/contact-form";
import { FramePanel } from "@/components/ui/frame-panel";
import { RuneMark } from "@/components/ui/rune-mark";

export const metadata: Metadata = {
  title: "Contact - Obsidura",
  description:
    "Get in touch with Obsidura — book a demo, ask about deployment, or partner with us.",
};

export default function ContactPage() {
  return (
    <>
      <Nav />
      <main className="flex-1">
        <section className="relative overflow-hidden">
          <div className="mx-auto grid max-w-6xl gap-12 px-5 pt-16 pb-20 lg:grid-cols-[1fr_1.15fr] lg:gap-16 lg:pt-24 lg:pb-28">
            <div>
              <p className="kicker mb-6 text-accent">
                05 &mdash; open a channel
              </p>
              <h1 className="font-display text-[clamp(2.75rem,6vw,4.5rem)] leading-[1.02] font-light tracking-tight">
                Tell us what you are{" "}
                <span className="headline-emph">trying to run.</span>
              </h1>
              <p className="mt-7 max-w-md font-mono text-sm leading-relaxed text-ink-soft">
                Design partners, deployment questions, or a thirty-minute demo
                — send a note and we will route it to the right person.
              </p>

              <div className="mt-10 space-y-4">
                <FramePanel className="inline-block bg-paper-warm/40 px-4 py-3">
                  <p className="kicker flex items-center gap-2.5">
                    <RuneMark size={10} />
                    contact@obsidura.com
                  </p>
                </FramePanel>
                <p className="font-mono text-[12px] leading-relaxed text-ink-mute">
                  Prefer email directly? That address lands in the same inbox.
                </p>
              </div>
            </div>

            <ContactForm />
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
