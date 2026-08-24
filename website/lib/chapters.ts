import type { EngravingName } from "@/lib/engravings";

export type Chapter = {
  slug: string;
  /** Lowercase roman numeral - kickers uppercase it in CSS. */
  numeral: string;
  /** The mythic name, kept as texture in kickers and the index. */
  name: string;
  headlineLead: string;
  headlineEmph: string;
  lede: string;
  /** One line for the homepage index. */
  blurb: string;
  /** Omitted when the chapter's body carries its own engravings. */
  art?: EngravingName;
  /** How tall the chapter's engraving is allowed to stand. */
  artHeight?: number;
  title: string;
  description: string;
};

/**
 * The five chapters, in reading order. The homepage index, the nav, the
 * prev/next pager, and the sitemap all derive from this list, so a chapter
 * cannot end up reachable from one and missing from another.
 */
export const CHAPTERS: Chapter[] = [
  {
    slug: "automations",
    numeral: "i",
    name: "the works",
    headlineLead: "One layer beneath.",
    headlineEmph: "Four kinds of work on top.",
    lede: "A company's information is scattered across dozens of places - databases, spreadsheets, mail, cloud tools, internal sites. Pantheon reaches them through the interfaces they already expose, aggregates what they hold into one governed layer, and sets agents to work against it: cron jobs that recur on a schedule, actions fired once, workflows that carry a process end to end, and questions asked in plain English, answered from the context of your data. Anything software and data can touch is in range.",
    blurb: "The four kinds of work that run on the layer, and the range of what they can be.",
    art: "olympus",
    artHeight: 620,
    title: "Automations - What Pantheon Runs | Obsidura",
    description:
      "Pantheon aggregates the systems your information is scattered across into one governed data layer, with agents working against it: cron jobs on a schedule, one-off actions, whole workflows, and plain-English questions answered from your data.",
  },
  {
    slug: "workflows",
    numeral: "ii",
    name: "the labors",
    headlineLead: "Workflows are data,",
    headlineEmph: "not code.",
    lede: "Every automation here is a set of YAML definitions that compile into a typed graph before anything runs. They diff in review like any other file, and a mismatched pair of tasks is caught when you plan, not at three in the morning when it runs. The engine never grows a branch for your business, so your hundredth automation costs what your first did.",
    blurb: "Every automation is inert data, compiled into a typed graph, with every edge derived rather than drawn.",
    art: "herakles",
    artHeight: 700,
    title: "Workflows - Definitions Are Data | Obsidura",
    description:
      "Tenant-authored YAML compiles into a typed graph in Postgres. Four primitives, five kernel values, no expression language, and edges derived from references.",
  },
  {
    slug: "governance",
    numeral: "iii",
    name: "the ledger",
    headlineLead: "Two people ask the same question.",
    headlineEmph: "They get different answers.",
    lede: "Permissions are not a filter an agent is asked politely to respect. Every resource call goes through a proxy holding the credentials, checked against the grants minted for that run, and the container never sees a secret at all. An automation can only ever touch what the person who asked for it could have touched themselves.",
    blurb: "Run-scoped permissions, and an append-only log that answers for them.",
    art: "athena-owl",
    artHeight: 560,
    title: "Governance - Scoped Access and the Run Log | Obsidura",
    description:
      "A run-scoped resource proxy enforces per-user grants on every call, and one append-only run log carries status, audit, approval, and crash recovery.",
  },
  {
    slug: "runtime",
    numeral: "iv",
    name: "the forge",
    headlineLead: "Automation shouldn't",
    headlineEmph: "feel fragile.",
    lede: "The reliability is forged in the runtime. We engineer the orchestration layer the way Hephaestus forged armor for the gods - like an operating system, not a chatbot - so agents keep working when models misbehave and upstreams slow down.",
    blurb: "Why a run survives bad model output, slow upstreams, and a killed executor.",
    art: "hephaestus",
    artHeight: 680,
    title: "Runtime - Durable Agent Execution | Obsidura",
    description:
      "A Rust executor over an append-only run log, warm container workers speaking JSON-RPC over stdio, schema validation at every seam, and bounded repair for agent output.",
  },
  {
    slug: "deploy",
    numeral: "v",
    name: "the dominions",
    headlineLead: "Your data stays",
    headlineEmph: "in your dominion.",
    lede: "Run Pantheon fully managed, inside your own cloud account, or on hardware that makes no outbound calls at all. When the war was won, the brothers drew lots for the cosmos - the heavens, the sea, the world below. Choose your dominion; the agents serve in all three.",
    blurb: "Managed, in your own VPC, or on hardware that never calls out.",
    title: "Deployment - Cloud, Private VPC, or On-Premises | Obsidura",
    description:
      "Deploy Pantheon in Obsidura Cloud, single-tenant in your own AWS or GCP account, or fully on-premises with no outbound calls.",
  },
];

export function chapterAt(slug: string) {
  const index = CHAPTERS.findIndex((c) => c.slug === slug);
  return {
    chapter: CHAPTERS[index],
    prev: CHAPTERS[index - 1],
    next: CHAPTERS[index + 1],
  };
}
