"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { FramePanel } from "@/components/ui/frame-panel";
import { MeanderMark } from "@/components/ui/meander-mark";
import {
  RESOURCE_EXAMPLES,
  SEED_CONNECTIONS,
  SERVICES,
  serviceById,
  type Connection,
  type Identity,
  type Service,
} from "@/lib/connections";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Small shared pieces                                                 */
/* ------------------------------------------------------------------ */

function Health({ health }: { health: Connection["health"] }) {
  const filled = health === "healthy";
  return (
    <span className="flex items-center gap-2 font-mono text-[11px] text-ink-mute">
      <span
        aria-hidden
        className={cn(
          "inline-block size-[7px] border",
          filled ? "border-ink bg-ink" : "border-ink-mute"
        )}
      />
      {health}
    </span>
  );
}

function Line({ mark, children }: { mark?: string; children: React.ReactNode }) {
  return (
    <p className="font-mono text-[11px] leading-relaxed break-words text-ink-mute">
      {mark && <span className="text-ink">{mark}&nbsp;&nbsp;</span>}
      {children}
    </p>
  );
}

function GhostButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="kicker border border-rule px-3.5 py-2 !text-[10px] transition-colors hover:border-accent-deep hover:text-ink"
    >
      {children}
    </button>
  );
}

function SolidButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="kicker bg-accent px-4 py-2.5 !text-[10px] !text-paper transition-colors hover:bg-ink-soft disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Screens                                                             */
/* ------------------------------------------------------------------ */

function IndexView({
  connections,
  onAdd,
  onOpen,
}: {
  connections: Connection[];
  onAdd: () => void;
  onOpen: (name: string) => void;
}) {
  return (
    <div>
      <ul className="divide-y divide-rule">
        {connections.map((c) => {
          const service = serviceById(c.serviceId);
          return (
            <li key={c.name}>
              <button
                type="button"
                onClick={() => onOpen(c.name)}
                className="group grid w-full grid-cols-1 gap-2 px-5 py-4 text-left transition-colors hover:bg-paper-warm/60 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-6"
              >
                <span className="flex items-center gap-3">
                  <MeanderMark size={9} className="shrink-0 text-ink-faint" />
                  <span className="font-mono text-[13px] text-ink">
                    {c.name}
                  </span>
                  <span className="kicker !text-[9px] text-accent">
                    {service.label}
                  </span>
                </span>
                <span className="pl-6 font-mono text-[10.5px] text-ink-faint sm:pl-0">
                  {c.referencedBy.length > 0
                    ? `referenced by: ${c.referencedBy.join(", ")}`
                    : "not yet referenced by a resource"}
                </span>
                <span className="flex items-center gap-5 pl-6 sm:pl-0">
                  <span className="kicker hidden !text-[9px] text-ink-faint md:inline">
                    {c.identity}
                  </span>
                  <Health health={c.health} />
                  <span className="font-mono text-[10.5px] text-ink-faint">
                    {c.lastCall}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="flex items-center justify-between border-t border-rule px-5 py-3.5">
        <p className="font-mono text-[10.5px] text-ink-faint">
          {connections.length} connections · secrets in executor custody
        </p>
        <GhostButton onClick={onAdd}>+ connect a service</GhostButton>
      </div>
    </div>
  );
}

function AddView({
  taken,
  onCancel,
  onContinue,
}: {
  taken: string[];
  onCancel: () => void;
  onContinue: (serviceId: string, identity: Identity, name: string) => void;
}) {
  const [serviceId, setServiceId] = useState<string | null>(null);
  const [identity, setIdentity] = useState<Identity>("service");
  const [name, setName] = useState("");

  const service = serviceId ? serviceById(serviceId) : null;
  const suggested = service ? `${service.id}-prod` : "";
  const finalName = (name.trim() || suggested).toLowerCase();
  const collision = taken.includes(finalName);

  function pick(s: Service) {
    setServiceId(s.id);
    setIdentity(s.identities.includes("delegated") ? "delegated" : "service");
    setName("");
  }

  return (
    <div className="px-5 py-5">
      <div className="grid gap-px sm:grid-cols-2 lg:grid-cols-4">
        {SERVICES.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => pick(s)}
            aria-pressed={serviceId === s.id}
            className={cn(
              "flex flex-col gap-1.5 border px-4 py-3.5 text-left transition-colors",
              serviceId === s.id
                ? "border-accent-deep bg-paper"
                : "border-rule hover:border-accent-deep"
            )}
          >
            <span className="font-display text-lg leading-tight font-light tracking-tight">
              {s.label}
            </span>
            <span className="font-mono text-[10px] text-ink-mute">
              {s.connector}
            </span>
            {s.covers && (
              <span className="font-mono text-[10px] text-ink-faint">
                {s.covers}
              </span>
            )}
            <span className="kicker mt-1 !text-[9px] text-accent">
              {s.lane}
              {s.phase !== "shipped" && ` · arrives ${s.phase}`}
            </span>
          </button>
        ))}
      </div>

      {service && (
        <div className="mt-5 border-t border-rule pt-5">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-4">
              <div>
                <p className="kicker mb-2 !text-[10px]">identity</p>
                <div className="flex flex-wrap gap-2">
                  {(["delegated", "service", "both"] as const).map((mode) => {
                    const allowed = service.identities.includes(mode);
                    return (
                      <button
                        key={mode}
                        type="button"
                        disabled={!allowed}
                        aria-pressed={identity === mode}
                        onClick={() => setIdentity(mode)}
                        className={cn(
                          "kicker border px-3 py-1.5 !text-[10px] transition-colors",
                          identity === mode
                            ? "border-accent-deep text-ink"
                            : "border-rule",
                          allowed
                            ? "hover:border-accent-deep hover:text-ink"
                            : "cursor-not-allowed opacity-35"
                        )}
                      >
                        {mode}
                      </button>
                    );
                  })}
                </div>
                <p className="mt-2 font-mono text-[10.5px] text-ink-faint">
                  {identity === "delegated"
                    ? "users consent individually — runs act as the person who asked"
                    : identity === "service"
                      ? "one app credential, narrowed per user by grants"
                      : "delegated when a requester is present, service otherwise"}
                </p>
              </div>
              <div>
                <label htmlFor="conn-name" className="kicker mb-2 block !text-[10px]">
                  name
                </label>
                <input
                  id="conn-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={suggested}
                  className="w-56 border border-rule bg-paper px-3 py-2 font-mono text-[12px] text-ink transition-colors placeholder:text-ink-faint focus:border-accent-deep"
                />
                {collision && (
                  <p className="mt-2 font-mono text-[10.5px] text-ink-mute">
                    a connection named &lsquo;{finalName}&rsquo; already exists
                  </p>
                )}
              </div>
            </div>
            <div className="flex shrink-0 gap-3">
              <GhostButton onClick={onCancel}>cancel</GhostButton>
              <SolidButton
                disabled={collision}
                onClick={() => onContinue(service.id, identity, finalName)}
              >
                {service.auth === "oauth consent"
                  ? "continue → consent"
                  : "continue → credential"}
              </SolidButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const VERIFY_STEP_MS = 700;

function VerifyView({
  service,
  name,
  identity,
  onDone,
}: {
  service: Service;
  name: string;
  identity: Identity;
  onDone: () => void;
}) {
  const reduced = useReducedMotion();
  const [step, setStep] = useState(0);

  const lines = [
    service.auth === "oauth consent"
      ? `granted by ${identity === "delegated" ? "each user, individually" : "the workspace admin"} · token pair received`
      : "received · written to executor custody",
    `${service.probe} · allowed · 213ms · 1 call`,
    "secret held by the executor — never a container, never YAML",
  ];
  const marks = [
    service.auth === "oauth consent" ? "consent" : "credential",
    "probe",
    "custody",
  ];

  useEffect(() => {
    if (reduced || step > lines.length) return;
    const id = window.setTimeout(() => setStep((s) => s + 1), VERIFY_STEP_MS);
    return () => window.clearTimeout(id);
  }, [reduced, step, lines.length]);

  const shown = reduced ? lines.length + 1 : step;
  const done = shown > lines.length;
  const resource = RESOURCE_EXAMPLES[service.id];

  return (
    <div className="px-5 py-5">
      <div className="space-y-2">
        {lines.slice(0, Math.min(shown, lines.length)).map((line, i) => (
          <Line key={line} mark={marks[i]}>
            {line}
          </Line>
        ))}
        {!done && (
          <p aria-hidden className="animate-pulse font-mono text-[11px] text-accent">
            &#9608;
          </p>
        )}
        {done && (
          <p className="flex items-center gap-2 font-mono text-[11px] text-ink">
            <span aria-hidden className="inline-block size-[7px] border border-ink bg-ink" />
            connection healthy
          </p>
        )}
      </div>

      {done && (
        <div className="mt-6 grid gap-5 border-t border-rule pt-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div>
            <p className="kicker mb-3 !text-[10px]">
              next: make it reachable — a resource definition, through review
            </p>
            <pre className="overflow-x-auto border border-rule bg-paper px-4 py-3.5 font-mono text-[11px] leading-relaxed whitespace-pre text-ink-soft">
              {`kind: resource
name: ${resource.name}
connector: ${resource.connector}
connection: ${name}
verbs: ${resource.verbs}`}
            </pre>
            <p className="mt-3 font-mono text-[10.5px] text-ink-faint">
              ptn plan && ptn apply &mdash; setup is self-serve; reachability
              is reviewed.
            </p>
          </div>
          <SolidButton onClick={onDone}>add to the wall &rarr;</SolidButton>
        </div>
      )}
    </div>
  );
}

const GRANT_USERS = ["u_okafor", "u_reyes", "u_ibarra", "u_chen"];

function DetailView({
  connection,
  onRevoke,
  onReauthorize,
  onAddGrant,
}: {
  connection: Connection;
  onRevoke: () => void;
  onReauthorize: () => void;
  onAddGrant: () => void;
}) {
  const service = serviceById(connection.serviceId);
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div className="flex flex-wrap items-center gap-4">
          <span className="font-mono text-[13px] text-ink">
            {connection.name}
          </span>
          <span className="kicker !text-[9px] text-accent">
            {service.label} · {service.connector}
          </span>
          <span className="kicker !text-[9px] text-ink-faint">
            {connection.identity}
          </span>
          <Health health={connection.health} />
        </div>
        <div className="flex gap-3">
          {connection.health === "token stale" && (
            <GhostButton onClick={onReauthorize}>reauthorize</GhostButton>
          )}
          {connection.health !== "revoked" && (
            <GhostButton onClick={onRevoke}>revoke</GhostButton>
          )}
        </div>
      </div>

      <div className="space-y-2 border-t border-rule px-5 py-4">
        <Line mark="referenced by">
          {connection.referencedBy.length > 0
            ? connection.referencedBy.join(", ")
            : `nothing yet — declare a resource with connection: ${connection.name}`}
        </Line>
        {connection.health === "revoked" && (
          <Line mark="revoked">
            <span className="text-ink underline underline-offset-4">
              referencing resources are stale
            </span>{" "}
            · the next run fails typed, not silently
          </Line>
        )}
      </div>

      <div className="border-t border-rule">
        <p className="kicker border-b border-rule px-5 py-2.5 !text-[10px] text-accent">
          grants &mdash; scope in the connector&rsquo;s own grammar:{" "}
          {service.scope}
        </p>
        <ul className="divide-y divide-rule">
          {connection.grants.map((g) => (
            <li
              key={`${g.user}-${g.scope}`}
              className="grid gap-1 px-5 py-3 sm:grid-cols-[7rem_9rem_minmax(0,1fr)] sm:gap-4"
            >
              <span className="font-mono text-[11px] text-ink">{g.user}</span>
              <span className="font-mono text-[11px] text-ink-mute">
                verbs [{g.verbs}]
              </span>
              <span className="font-mono text-[11px] break-words text-ink-mute">
                scope {g.scope}
              </span>
            </li>
          ))}
        </ul>
        <div className="border-t border-rule px-5 py-3">
          <GhostButton onClick={onAddGrant}>+ add grant</GhostButton>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* The surface                                                         */
/* ------------------------------------------------------------------ */

type View =
  | { screen: "index" }
  | { screen: "add" }
  | { screen: "verify"; serviceId: string; identity: Identity; name: string }
  | { screen: "detail"; name: string };

/**
 * The Connections surface from the connectors spec (§8), run against
 * local state the way the reports demo runs a fake run: every screen,
 * transition, and log line is the designed behavior, with nothing real
 * behind it. Add a connection and it joins the wall; revoke one and its
 * referencing resources go visibly stale.
 */
export function ConnectionsSurface() {
  const reduced = useReducedMotion();
  const [connections, setConnections] = useState<Connection[]>(SEED_CONNECTIONS);
  const [view, setView] = useState<View>({ screen: "index" });

  const title =
    view.screen === "index"
      ? "the wall"
      : view.screen === "add"
        ? "connect a service"
        : view.screen === "verify"
          ? `verifying ${view.name}`
          : view.name;

  function mutate(name: string, patch: Partial<Connection>) {
    setConnections((cs) =>
      cs.map((c) => (c.name === name ? { ...c, ...patch } : c))
    );
  }

  const current =
    view.screen === "detail"
      ? connections.find((c) => c.name === view.name)
      : undefined;

  return (
    <FramePanel className="bg-paper-warm/30">
      <div className="flex items-center justify-between gap-4 border-b border-rule px-5 py-2.5">
        <p className="kicker flex items-center gap-2.5 !text-[10px] text-accent">
          <MeanderMark size={9} />
          connections &mdash; {title}
        </p>
        {view.screen !== "index" && view.screen !== "verify" && (
          <button
            type="button"
            onClick={() => setView({ screen: "index" })}
            className="kicker !text-[10px] text-ink-mute transition-colors hover:text-ink"
          >
            &larr; the wall
          </button>
        )}
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={view.screen + (view.screen === "detail" ? view.name : "")}
          initial={reduced ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduced ? undefined : { opacity: 0, y: -6 }}
          transition={{ duration: 0.25, ease: [0.21, 0.47, 0.32, 0.98] }}
        >
          {view.screen === "index" && (
            <IndexView
              connections={connections}
              onAdd={() => setView({ screen: "add" })}
              onOpen={(name) => setView({ screen: "detail", name })}
            />
          )}

          {view.screen === "add" && (
            <AddView
              taken={connections.map((c) => c.name)}
              onCancel={() => setView({ screen: "index" })}
              onContinue={(serviceId, identity, name) =>
                setView({ screen: "verify", serviceId, identity, name })
              }
            />
          )}

          {view.screen === "verify" && (
            <VerifyView
              service={serviceById(view.serviceId)}
              name={view.name}
              identity={view.identity}
              onDone={() => {
                setConnections((cs) => [
                  ...cs,
                  {
                    name: view.name,
                    serviceId: view.serviceId,
                    identity: view.identity,
                    health: "healthy",
                    referencedBy: [],
                    lastCall: "just now",
                    grants: [],
                  },
                ]);
                setView({ screen: "index" });
              }}
            />
          )}

          {view.screen === "detail" && current && (
            <DetailView
              connection={current}
              onRevoke={() => mutate(current.name, { health: "revoked" })}
              onReauthorize={() => mutate(current.name, { health: "healthy" })}
              onAddGrant={() =>
                mutate(current.name, {
                  grants: [
                    ...current.grants,
                    {
                      user: GRANT_USERS[current.grants.length % GRANT_USERS.length],
                      verbs: "get",
                      scope: serviceById(current.serviceId).scopeExample,
                    },
                  ],
                })
              }
            />
          )}
        </motion.div>
      </AnimatePresence>
    </FramePanel>
  );
}
