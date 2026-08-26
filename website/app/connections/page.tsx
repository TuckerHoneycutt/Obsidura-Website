import type { Metadata } from "next";
import Link from "next/link";
import { ConnectionsSurface } from "@/components/connections-surface";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderDivider, MeanderMark } from "@/components/ui/meander-mark";
import { Reveal } from "@/components/ui/reveal";
import { SERVICES } from "@/lib/connections";

export const metadata: Metadata = {
  title: "Connections - Set Up What Pantheon Reaches | Obsidura",
  description:
    "The designed v1 surface for connecting Pantheon to Google Workspace, Microsoft 365, Slack, Jira, Azure, a NAS, databases, and MCP servers - self-serve setup, reviewed reachability, and grants written in each service's own terms.",
  alternates: { canonical: "/connections" },
};

const CONTRACT = [
  {
    q: "transport + auth",
    a: "How the proxy reaches the service, and what secret it custodies. Custody is always executor-side; a container only ever holds the socket.",
  },
  {
    q: "verbs",
    a: "The closed set of operations a resource may expose - query, get, put, search, post. Declared in the definition, enforced per grant.",
  },
  {
    q: "scope grammar",
    a: "How a grant narrows the service in the service's own terms. “Full access” is not a grammar.",
  },
  {
    q: "audit shape",
    a: "What one call writes to the run log: verb, target, the scope decision - including denials - and what moved, by handle.",
  },
];

export default function ConnectionsPage() {
  return (
    <main className="flex-1">
      {/* Hero */}
      <section className="relative">
        <div className="mx-auto max-w-6xl px-5 pt-16 lg:pt-24">
          <Reveal className="max-w-3xl">
            <p className="kicker mb-6 text-accent">
              connections &mdash; the v1 surface, designed
            </p>
            <h1 className="font-display text-[clamp(2.2rem,4.8vw,3.5rem)] leading-[1.04] font-light tracking-tight">
              Connections to the places{" "}
              <span className="headline-emph">your information lives.</span>
            </h1>
            <p className="lede-copy mt-6 max-w-xl">
              Google Workspace, Microsoft 365, Slack, Jira, Azure, a NAS, a
              database &mdash; connected in a consent screen, not a code
              review. Then parsed into typed data your automations can report
              on and answer questions about, under the same proxy, grants,
              and audit log as everything else.
            </p>
          </Reveal>

          {/* The honesty strip: this page is a design, not a shipped list. */}
          <Reveal delay={0.08}>
            <FramePanel className="mt-10 max-w-3xl bg-paper-warm/40">
              <p className="body-copy-sm px-5 py-4 text-ink-mute">
                Today the engine ships three connector kinds &mdash;
                Postgres, object storage, and HTTP. What follows is the v1
                connector surface as specified, arriving in phases; this page
                will say so as each one lands, and not before.
              </p>
            </FramePanel>
          </Reveal>
        </div>
      </section>

      {/* The surface itself */}
      <section className="relative mt-16 border-t border-rule lg:mt-20">
        <MeanderDivider />
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <Reveal className="max-w-3xl">
            <p className="kicker text-accent">the surface</p>
            <h2 className="font-display mt-6 text-[clamp(1.65rem,3.2vw,2.5rem)] leading-[1.08] font-light tracking-tight">
              Setup is self-serve,{" "}
              <span className="headline-emph">and reachability is reviewed.</span>
            </h2>
            <p className="body-copy mt-5 text-ink-mute">
              Four screens: the wall of connections, the catalog, the
              verification probe, and the grants. Try it &mdash; this is the
              designed behavior running against local state, with nothing
              real behind it. Connect a service and it joins the wall; revoke
              one and everything referencing it goes visibly stale.
            </p>
          </Reveal>
          <Reveal delay={0.1}>
            <div className="mt-10">
              <ConnectionsSurface />
            </div>
          </Reveal>
        </div>
      </section>

      {/* The contract */}
      <section className="relative border-t border-rule bg-paper-warm/40">
        <MeanderDivider />
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <Reveal className="max-w-3xl">
            <p className="kicker text-accent">the contract</p>
            <h2 className="font-display mt-6 text-[clamp(1.65rem,3.2vw,2.5rem)] leading-[1.08] font-light tracking-tight">
              Every connector answers{" "}
              <span className="headline-emph">four questions.</span>
            </h2>
            <p className="body-copy mt-5">
              A new service is never a new engine feature. Every connector
              &mdash; present or future &mdash; is fully described by four
              answers, registered as data. A connector that cannot answer all
              four is not ready to exist.
            </p>
          </Reveal>
          <div className="mt-10 grid gap-6 sm:grid-cols-2">
            {CONTRACT.map((item, i) => (
              <Reveal key={item.q} delay={Math.min(i * 0.06, 0.2)}>
                <FramePanel className="h-full bg-paper">
                  <p className="kicker border-b border-rule px-5 py-2.5 !text-[10px] text-accent">
                    {item.q}
                  </p>
                  <p className="body-copy-sm px-5 py-4">{item.a}</p>
                </FramePanel>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Connection vs resource */}
      <section className="relative border-t border-rule">
        <MeanderDivider />
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <div className="grid gap-10 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
            <Reveal>
              <p className="kicker text-accent">the split</p>
              <h2 className="font-display mt-6 text-[clamp(1.65rem,3.2vw,2.5rem)] leading-[1.08] font-light tracking-tight">
                A connection is{" "}
                <span className="headline-emph">not a resource.</span>
              </h2>
              <p className="body-copy mt-5">
                A <em>connection</em> is a credential and an endpoint &mdash;
                created in the surface above, held by the executor, never
                present in YAML, a diff, or a container. A <em>resource</em>{" "}
                is what jobs actually touch: a definition that references the
                connection by name and declares the verbs it exposes,
                entering through plan and apply like any other change.
              </p>
              <p className="body-copy mt-4 text-ink-mute">
                That split is what makes self-serve setup safe. Anyone
                permitted can connect their workspace; no job can reach it
                until a reviewed definition says so. Rotating or revoking a
                credential touches no definitions at all.
              </p>
            </Reveal>
            <Reveal delay={0.1}>
              <FramePanel className="bg-paper-warm/30">
                <p className="kicker border-b border-rule px-5 py-2.5 !text-[10px] text-accent">
                  the two halves
                </p>
                <div className="space-y-2 px-5 py-4">
                  <p className="font-mono text-[11px] leading-relaxed text-ink-mute">
                    <span className="text-ink">connection&nbsp;&nbsp;</span>
                    m365-prod · token pair · executor custody
                  </p>
                  <p className="font-mono text-[11px] leading-relaxed text-ink-mute">
                    created in the surface · no review · revocable in place
                  </p>
                </div>
                <div className="border-t border-rule px-5 py-4">
                  <pre className="overflow-x-auto font-mono text-[11px] leading-relaxed whitespace-pre text-ink-soft">
                    {`kind: resource
name: board-files@1
connector: ms.graph
connection: m365-prod
verbs: [get, list]`}
                  </pre>
                  <p className="mt-3 font-mono text-[10.5px] text-ink-faint">
                    ptn plan &amp;&amp; ptn apply &mdash; reviewed, like any
                    other change
                  </p>
                </div>
              </FramePanel>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Scope grammar table */}
      <section className="relative border-t border-rule bg-paper-warm/40">
        <MeanderDivider />
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <Reveal className="max-w-3xl">
            <p className="kicker text-accent">the catalog</p>
            <h2 className="font-display mt-6 text-[clamp(1.65rem,3.2vw,2.5rem)] leading-[1.08] font-light tracking-tight">
              Scope is granted in each service&rsquo;s{" "}
              <span className="headline-emph">own words.</span>
            </h2>
            <p className="body-copy mt-5">
              A grant never says &ldquo;full access.&rdquo; It narrows the
              service in the grammar the service itself understands &mdash;
              the same move as the row filter, the key prefix, and the URL
              allowlist that ship today. Grammars rhyme across connectors
              wherever the service allows it: the Jira grant is a JQL
              fragment ANDed onto every query, which is the Postgres row
              filter wearing different clothes.
            </p>
          </Reveal>
          <ul className="mt-10 grid gap-x-10 gap-y-px sm:grid-cols-2">
            {SERVICES.map((s, i) => (
              <Reveal key={s.id} delay={Math.min(i * 0.04, 0.24)}>
                <li className="flex flex-col gap-1.5 border-t border-rule py-5 sm:flex-row sm:gap-6">
                  <span className="kicker shrink-0 !text-[10px] text-accent sm:w-32">
                    {s.label}
                  </span>
                  <span className="body-copy-sm">
                    <span className="font-mono text-[11px] text-ink-mute">
                      {s.connector}
                    </span>{" "}
                    &mdash; {s.scope}
                  </span>
                </li>
              </Reveal>
            ))}
          </ul>
        </div>
      </section>

      {/* Parsing */}
      <section className="relative border-t border-rule">
        <MeanderDivider />
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <Reveal className="max-w-3xl">
            <p className="kicker text-accent">parsing</p>
            <h2 className="font-display mt-6 text-[clamp(1.65rem,3.2vw,2.5rem)] leading-[1.08] font-light tracking-tight">
              Files are parsed{" "}
              <span className="headline-emph">before agents read them.</span>
            </h2>
            <p className="body-copy mt-5">
              An agent never reads a binary. A spreadsheet from OneDrive, a
              PDF from the NAS, a mail thread &mdash; each lands in the blob
              store as a file, and a deterministic parser turns it into typed
              tables and records before any judgment is applied. Parsing is
              not a matter of opinion, so no model is involved.
            </p>
            <p className="body-copy mt-4 text-ink-mute">
              Every parsed value carries its provenance &mdash; which file,
              which version, fetched when &mdash; so a report can cite its
              inputs and an answer can say where it came from. This is what
              turns &ldquo;connected&rdquo; into &ldquo;can make reports and
              answer questions.&rdquo;
            </p>
            <div className="mt-8 flex flex-wrap gap-2">
              {["parse.xlsx", "parse.csv", "parse.pdf", "parse.eml"].map(
                (p) => (
                  <span
                    key={p}
                    className="flex items-center gap-2 border border-rule px-3 py-1.5 font-mono text-[11px] text-ink-mute"
                  >
                    <MeanderMark size={8} className="text-ink-faint" />
                    {p}
                  </span>
                )
              )}
            </div>
          </Reveal>
        </div>
      </section>

      {/* Further reading + CTA, composed as the subpages do */}
      <section className="relative border-t border-rule">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <Reveal className="border-rule">
            <p className="kicker mb-4">further reading</p>
            <div className="flex flex-wrap gap-x-8 gap-y-3">
              {[
                { label: "Integrations shipped today", href: "/integrations" },
                { label: "Governance and grants", href: "/governance" },
                { label: "Security model", href: "/security" },
                { label: "What Pantheon runs", href: "/automations" },
              ].map(({ label, href }) => (
                <Link
                  key={href}
                  href={href}
                  className="kicker link-sweep transition-colors hover:text-ink"
                >
                  {label} &rarr;
                </Link>
              ))}
            </div>
          </Reveal>
          <Reveal delay={0.08}>
            <FramePanel className="mt-14 bg-paper-warm/40">
              <div className="flex flex-col items-start gap-6 px-6 py-8 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="font-display text-3xl font-light tracking-tight">
                    Have a system we should reach first?
                  </h2>
                  <p className="body-copy mt-2 max-w-md text-ink-mute">
                    The catalog ships in phases, and design partners set the
                    order. Tell us what your work lives in.
                  </p>
                </div>
                <Link
                  href="/contact"
                  className="kicker inline-block shrink-0 bg-accent px-6 py-3.5 !text-paper transition-colors hover:bg-ink-soft"
                >
                  Book a demo
                </Link>
              </div>
            </FramePanel>
          </Reveal>
        </div>
      </section>
    </main>
  );
}
