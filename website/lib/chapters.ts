import type { EngravingName } from "@/lib/engravings";

export type Chapter = {
  slug: string;
  /** Lowercase roman numeral - kickers uppercase it in CSS. */
  numeral: string;
  /** The chapter's display name - the one label the nav dropdown, the
      homepage index, the pager, and the command palette all use. */
  label: string;
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
    label: "Pantheon",
    headlineLead: "What is",
    headlineEmph: "Pantheon?",
    lede: "Pantheon is a data layer for agents: it aggregates the data scattered across your systems into one secure, governed layer, and gives you a place to define, run, and manage the work that agents do against it - scripted tasks and AI agents in the same job, on a schedule or on demand. An agent may do the thinking, but the engine decides what your role lets it reach, checks what it produces, and keeps the record of what happened.",
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
    label: "Workflows",
    headlineLead: "Workflows are data,",
    headlineEmph: "not code.",
    lede: "Every automation is a set of YAML definitions that compile into a typed graph before anything runs. Definitions are reviewed like any other file, and mismatched tasks are caught when the definition is planned, not when it runs. The engine itself never changes for your business, so the cost of adding automations stays flat.",
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
    label: "Roles and Permissions",
    headlineLead: "Answers depend on",
    headlineEmph: "who is asking.",
    lede: "Every resource call goes through a proxy that holds the credentials and checks the call against the grants issued for that run; the container never sees a secret. An automation can only touch what the person who requested it is allowed to touch.",
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
    label: "Reliability",
    headlineLead: "How runs survive",
    headlineEmph: "failure.",
    lede: "The orchestration layer is engineered for reliability: agents keep working when models return bad output, upstream systems slow down, or a machine fails mid-run.",
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
    label: "Deploy",
    headlineLead: "Cloud, private VPC,",
    headlineEmph: "or on-premises.",
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
