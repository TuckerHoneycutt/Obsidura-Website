/**
 * The connector catalog and demo state for the Connections surface -
 * the data mirror of specs/pantheon-connectors-v1.md. The catalog is the
 * spec's §4 table; the seed connections are §8.1's wall. One source, so
 * the page's prose, the surface, and the spec cannot drift apart.
 */

export type Identity = "delegated" | "service" | "both";

export type Service = {
  id: string;
  label: string;
  connector: string;
  /** Which of the spec's three lanes the connector arrives through. */
  lane: "http profile" | "family" | "mcp";
  auth: "oauth consent" | "credential";
  /** What one connection opens up, when it is more than the name says. */
  covers?: string;
  /** The grant grammar, in the service's own terms (spec §4). */
  scope: string;
  /** A grant written in that grammar, for the grants editor. */
  scopeExample: string;
  /** The least-privilege probe the verify step performs (spec §8.3). */
  probe: string;
  /** Identity modes the connection supports (spec §5). */
  identities: Identity[];
  /** Build-plan phase it ships in (spec §11). */
  phase: string;
};

export const SERVICES: Service[] = [
  {
    id: "google",
    label: "Google Workspace",
    connector: "google.*",
    lane: "http profile",
    auth: "oauth consent",
    covers: "Drive · Sheets · Gmail · Calendar",
    scope: "folder-ID prefix · spreadsheet ID + range · label or query filter",
    scopeExample: "drive:finance-shared path:/board/*",
    probe: "drive.list  /shared-drives",
    identities: ["delegated", "service", "both"],
    phase: "C2",
  },
  {
    id: "m365",
    label: "Microsoft 365",
    connector: "ms.graph",
    lane: "http profile",
    auth: "oauth consent",
    covers: "SharePoint · OneDrive · live Excel · Outlook",
    scope: "site ID · drive ID · path prefix · workbook + range",
    scopeExample: "site:finance path:/board/*",
    probe: "graph.get  /me/drive/root",
    identities: ["delegated", "service", "both"],
    phase: "C2",
  },
  {
    id: "slack",
    label: "Slack",
    connector: "slack",
    lane: "http profile",
    auth: "oauth consent",
    covers: "read · post · trigger on mention",
    scope: "channel allowlist",
    scopeExample: "channels:#eng-standup,#releases",
    probe: "slack.list  /conversations",
    identities: ["service"],
    phase: "C5",
  },
  {
    id: "jira",
    label: "Jira",
    connector: "jira",
    lane: "http profile",
    auth: "oauth consent",
    covers: "read · file issues · trigger on transition",
    scope: "project keys + a JQL fragment ANDed onto every query",
    scopeExample: "projects:OPS,INF jql:(status != Done)",
    probe: "jira.search  project in (OPS)",
    identities: ["service"],
    phase: "C5",
  },
  {
    id: "postgres",
    label: "Postgres",
    connector: "postgres",
    lane: "family",
    auth: "credential",
    covers: "MySQL · SQL Server · Azure SQL join the family",
    scope: "SQL row filter",
    scopeExample: "entity = 'north'",
    probe: "postgres.query  select 1",
    identities: ["service"],
    phase: "shipped",
  },
  {
    id: "azure",
    label: "Azure",
    connector: "azure.blob / azure.sql",
    lane: "family",
    auth: "credential",
    covers: "Blob storage · Azure SQL · ARM via http",
    scope: "container + key prefix · row filter · resource-group allowlist",
    scopeExample: "container:receipts prefix:2026/",
    probe: "blob.list  receipts/",
    identities: ["service"],
    phase: "C6",
  },
  {
    id: "nas",
    label: "NAS (SMB)",
    connector: "smb",
    lane: "family",
    auth: "credential",
    covers: "the s3 grammar, applied to a filesystem",
    scope: "share + path prefix",
    scopeExample: "share:finance path:/receipts/*",
    probe: "smb.list  //finance",
    identities: ["service"],
    phase: "C6",
  },
  {
    id: "mcp",
    label: "MCP server",
    connector: "mcp",
    lane: "mcp",
    auth: "credential",
    covers: "the long tail, one connector kind",
    scope: "tool allowlist + argument constraints",
    scopeExample: "tools:search_tickets,get_ticket",
    probe: "mcp.list_tools",
    identities: ["service"],
    phase: "C7",
  },
];

export type Grant = {
  user: string;
  verbs: string;
  scope: string;
};

export type Connection = {
  name: string;
  serviceId: string;
  identity: Identity;
  health: "healthy" | "token stale" | "revoked";
  referencedBy: string[];
  lastCall: string;
  grants: Grant[];
};

/** The wall as the spec sketches it (§8.1), before the visitor adds to it. */
export const SEED_CONNECTIONS: Connection[] = [
  {
    name: "workspace-prod",
    serviceId: "google",
    identity: "both",
    health: "healthy",
    referencedBy: ["crm.docs@2", "board-pack@1"],
    lastCall: "2m ago",
    grants: [
      { user: "u_ellis", verbs: "get, list", scope: "drive:finance-shared path:/board/*" },
      { user: "u_okafor", verbs: "get", scope: "drive:finance-shared path:/board/q*" },
    ],
  },
  {
    name: "crm-replica",
    serviceId: "postgres",
    identity: "service",
    health: "healthy",
    referencedBy: ["crm.db@1"],
    lastCall: "11m ago",
    grants: [
      { user: "u_ellis", verbs: "query", scope: "entity = 'north'" },
      { user: "u_okafor", verbs: "query", scope: "entity = 'south'" },
    ],
  },
  {
    name: "eng-slack",
    serviceId: "slack",
    identity: "service",
    health: "token stale",
    referencedBy: ["standup-digest@1"],
    lastCall: "3d ago",
    grants: [
      { user: "u_reyes", verbs: "read, post", scope: "channels:#eng-standup" },
    ],
  },
  {
    name: "finance-nas",
    serviceId: "nas",
    identity: "service",
    health: "healthy",
    referencedBy: ["receipts.archive@1"],
    lastCall: "1h ago",
    grants: [
      { user: "u_ellis", verbs: "get, list", scope: "share:finance path:/receipts/*" },
    ],
  },
];

export function serviceById(id: string): Service {
  return SERVICES.find((s) => s.id === id) ?? SERVICES[0];
}

/**
 * The resource definition the verify screen suggests (spec §8.3) - the
 * YAML half of the Connection/Resource split, one example per service.
 */
export const RESOURCE_EXAMPLES: Record<
  string,
  { name: string; connector: string; verbs: string }
> = {
  google: { name: "board-files@1", connector: "google.drive", verbs: "[get, list]" },
  m365: { name: "board-files@1", connector: "ms.graph", verbs: "[get, list]" },
  slack: { name: "eng-channels@1", connector: "slack", verbs: "[read, post]" },
  jira: { name: "ops-board@1", connector: "jira", verbs: "[search, get]" },
  postgres: { name: "crm.db@1", connector: "postgres", verbs: "[query]" },
  azure: { name: "receipts.blob@1", connector: "azure.blob", verbs: "[get, list]" },
  nas: { name: "receipts.archive@1", connector: "smb", verbs: "[get, list]" },
  mcp: { name: "ticket-tools@1", connector: "mcp", verbs: "[call]" },
};
