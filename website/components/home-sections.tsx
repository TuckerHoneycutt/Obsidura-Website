"use client";

import Link from "next/link";
import { BackgroundRippleEffect } from "@/components/ui/background-ripple-effect";
import { FlipWords } from "@/components/ui/flip-words";
import { GlowingEffect } from "@/components/ui/glowing-effect";
import { InfiniteMovingCards } from "@/components/ui/infinite-moving-cards";
import { LampContainer } from "@/components/ui/lamp";
import { MeanderDivider } from "@/components/ui/meander-mark";
import { Button as MovingBorderButton } from "@/components/ui/moving-border";
import { Reveal } from "@/components/ui/reveal";
import { romanNumeral } from "@/lib/utils";

/*
 * The homepage sections below the hero. Every line of copy here is already
 * said elsewhere on the site - the hero, the FAQ, the security page - so the
 * page gains depth without making a single claim the site did not already
 * make. The engine's internals stay off it, as before.
 */

const h2 =
  "font-display text-[clamp(2rem,4vw,3.25rem)] leading-[1.06] font-light tracking-tight";

// From the FAQ's "What is small software?" and "What kinds of work can it run?"
const EXAMPLES = [
  "A tracker for the numbers your team actually watches.",
  "A workflow tool shaped to how you actually work.",
  "A prototype you want colleagues to try today.",
  "A month-end performance pack.",
  "A nightly reconciliation.",
  "A team workflow carried end to end.",
  "A question asked in plain English and answered from your data.",
].map((quote, i) => ({ quote, title: `small software · ${romanNumeral(i + 1)}` }));

export function SmallSoftware() {
  return (
    <section className="relative border-t border-rule py-20 lg:py-28">
      <MeanderDivider />
      <Reveal className="mx-auto max-w-3xl px-5 text-center">
        <p className="kicker mb-5 text-accent">what small software is</p>
        <h2 className={h2}>
          Tools that will only ever have{" "}
          <span className="headline-emph">a handful of users.</span>
        </h2>
        <p className="lede-copy mx-auto mt-6 max-w-xl">
          Agents have made this kind of software easy to build. Deploying,
          securing, and sharing it is the part that has stayed hard - and the
          part we solve.
        </p>
      </Reveal>
      <InfiniteMovingCards items={EXAMPLES} speed="slow" className="mt-14" />
    </section>
  );
}

// From the security page and the FAQ, one promise per card.
const PILLARS = [
  {
    kicker: "build & deploy",
    title: "Agents get everything they need",
    body: "Pantheon gives agents everything they need to build, deploy, and run software across your organization - on a schedule, at the press of a button, or when another system calls in.",
  },
  {
    kicker: "secure",
    title: "Your tools never hold a credential",
    body: "The platform holds the credentials, makes each call on the tool's behalf, and hands back only the data - so there is no token to leak.",
  },
  {
    kicker: "share",
    title: "Access follows the person",
    body: "Two people can use the same tool and each only ever touches what they are allowed to touch, checked every time rather than once at the start.",
  },
  {
    kicker: "record",
    title: "Every run is recorded",
    body: "What ran, for whom, what it touched, and what it produced - so there is always an answer to what happened.",
  },
];

export function Pillars() {
  return (
    <section className="relative border-t border-rule py-20 lg:py-28">
      <MeanderDivider />
      <div className="mx-auto max-w-6xl px-5">
        <Reveal className="max-w-2xl">
          <p className="kicker mb-5 text-accent">what once was hard</p>
          <h2 className={h2}>
            Deploy, secure, and share{" "}
            <span className="headline-emph">- seamlessly.</span>
          </h2>
        </Reveal>

        <div className="mt-14 grid gap-4 md:grid-cols-2">
          {PILLARS.map(({ kicker, title, body }, i) => (
            <Reveal key={title} delay={i * 0.08} className="h-full">
              <div className="relative h-full border border-rule p-1.5">
                <GlowingEffect
                  spread={40}
                  glow
                  proximity={64}
                  inactiveZone={0.01}
                  borderWidth={2}
                />
                <div className="relative flex h-full flex-col gap-4 bg-paper-warm/50 p-7">
                  <p className="kicker flex items-center gap-3">
                    <span className="text-accent">{romanNumeral(i + 1)}</span>
                    {kicker}
                  </p>
                  <h3 className="font-display text-[1.75rem] leading-tight font-medium tracking-tight">
                    {title}
                  </h3>
                  <p className="body-copy">{body}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>

        <Link
          href="/security"
          transitionTypes={["nav-forward"]}
          className="kicker link-sweep mt-10 inline-block transition-colors hover:text-ink"
        >
          the security model &rarr;
        </Link>
      </div>
    </section>
  );
}

// From the FAQ's "Where can it run?"
const PLACES = ["our managed cloud", "your private VPC", "your own premises"];

export function WhereItRuns() {
  return (
    // The ripple field clips itself; the section must not, or it would cut
    // the meander seal that sits astride the top rule.
    <section className="relative border-t border-rule">
      <MeanderDivider className="z-20" />
      <BackgroundRippleEffect rows={8} cols={30} cellSize={56} />
      <div className="pointer-events-none relative z-10 mx-auto flex min-h-[28rem] max-w-4xl flex-col items-center justify-center px-5 py-24 text-center">
        <p className="kicker mb-5 text-accent">where it runs</p>
        <h2 className={h2}>
          Run it in
          <br />
          <FlipWords words={PLACES} className="headline-emph" />
        </h2>
        <p className="lede-copy mt-6 max-w-md">
          The security model is the same in all three.
        </p>
      </div>
    </section>
  );
}

export function ClosingCta() {
  return (
    <section className="relative border-t border-rule">
      <LampContainer>
        <Reveal className="flex flex-col items-center text-center">
          <p className="kicker mb-5 text-accent">getting started</p>
          <h2 className={h2}>
            Bring <span className="headline-emph">one use case.</span>
          </h2>
          <p className="lede-copy mt-6 max-w-lg">
            We map it on a 30-minute call and show you what it looks like
            running by the end of it.
          </p>
          <MovingBorderButton
            as={Link}
            href="/contact"
            duration={4000}
            containerClassName="mt-10"
            className="kicker !text-ink"
          >
            Book a demo
          </MovingBorderButton>
        </Reveal>
      </LampContainer>
    </section>
  );
}
