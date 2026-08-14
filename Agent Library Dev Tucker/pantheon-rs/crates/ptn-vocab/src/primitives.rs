//! The definition-graph primitives (spec §4): what *can* exist.
//!
//! Every type here carries a `kind:` discriminator matching its serde tag, so
//! the YAML a tenant authors and the Rust the executor holds share one
//! vocabulary (spec §7). Deferred variants -- `file_watch`, `socket`, `bus`
//! triggers; `imap`, `mcp`, `memory` connectors; the `model` runner -- are
//! deliberately absent rather than stubbed. An enum arm that exists but is
//! unimplemented is an invitation to author a definition that plans cleanly and
//! cannot run.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use crate::duration::GoDuration;
use crate::typeref::TypeRef;

/// One resource and the verbs a task needs on it.
///
/// This is the input to the grant check the proxy performs on every call
/// (spec §8). It is a static declaration on purpose: a resource name that
/// arrived at runtime could not be checked against it.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct ResourceUse {
    /// Name of the resource, matching a `Resource` definition.
    pub name: String,
    /// Verbs needed on it. Declare the minimum: a verb listed and never used is
    /// a permission carried for no reason.
    pub verbs: Vec<String>,
}

/// Per-task operational policy.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Policy {
    /// Wall-clock cap on one attempt.
    pub timeout: GoDuration,
    /// Retries after the first attempt. Requires `idempotent`.
    #[serde(default)]
    pub retry: u32,
    /// Whether running twice is safe. Retrying without this is how one failure
    /// becomes two ledger entries.
    #[serde(default)]
    pub idempotent: bool,
    /// Token budget. Meaningful only for an agent runner; carried regardless so
    /// both runner kinds share one policy shape.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub budget: Option<i64>,
}

/// How a task's body runs.
///
/// Spec §4: an agent is an ordinary task with extra policy, never a special
/// execution path. Same container, same protocol; the tag changes output
/// validation, token budget, taint recording and audit metadata -- nothing
/// about how the executor dispatches it.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Runner {
    /// A deterministic body.
    Script {
        /// `python`, `go`, ... A runtime is a runner image, not a special case
        /// in the executor: invariant 4 says swapping the harness must touch
        /// zero executor code.
        runtime: String,
        /// The action name the image dispatches on.
        entry: String,
    },
    /// A stochastic body. Same container and protocol as a script; the tag
    /// changes policy -- output validation with bounded repair, token budget,
    /// taint recording, audit metadata -- never the execution path.
    Agent {
        /// Ref of the `AgentSpec` value this task runs under.
        spec: TypeRef,
    },
}

/// A gate that suspends a run until a human answers (spec §4).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct ApprovalGate {
    /// User ids permitted to answer this gate.
    pub approvers: Vec<String>,
    /// How long the run waits before the gate expires.
    pub timeout: GoDuration,
}

/// A unit of work.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Task {
    /// Dotted, lower_snake identifier. The first segment is the vertical.
    pub name: String,
    /// Bumped on any incompatible change to input or output.
    pub version: u32,
    /// One line, in plain language. Becomes the deck's button label.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub summary: String,

    /// How the body runs.
    pub runner: Runner,
    /// Ref of the schema this task's input must validate against.
    pub input: TypeRef,
    /// Ref of the schema this task's output is validated against before
    /// anything downstream sees it (spec §6).
    pub output: TypeRef,

    /// Resources and verbs this task needs. Checked at plan time against what
    /// each resource declares, and again at run time by the proxy.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub uses: Vec<ResourceUse>,
    /// Timeout, retry and idempotence.
    pub policy: Policy,

    /// Trigger this task runs on. A wiring reference, authored in YAML.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub on: Option<TypeRef>,

    /// Task(s) that run next. A wiring reference, authored in YAML.
    ///
    /// Edges are DERIVED from `on:`/`then:`/`uses:`, never authored as
    /// entities (invariant 3). These fields are the references; the graph is
    /// what the registry computes from them.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub then: Vec<TypeRef>,

    /// Suspends the run until a human answers. Survives executor restart.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gate: Option<ApprovalGate>,
}

impl Task {
    /// The task's own `name@version`.
    pub fn type_ref(&self) -> TypeRef {
        TypeRef::new(self.name.clone(), self.version)
    }
}

/// What makes a run start (spec §4).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "source", rename_all = "snake_case")]
pub enum TriggerSource {
    /// Fires on a schedule.
    Cron {
        /// Cron expression, in the executor's timezone.
        schedule: String,
    },
    /// Fires when an HTTP endpoint is called.
    Webhook {
        /// URL path the webhook listens on.
        path: String,
    },
    /// API/CLI fire, used by tests and the demo shell.
    Manual,
}

/// A declared way for runs of a task to begin.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Trigger {
    /// Dotted identifier, e.g. `finance.audit_request`.
    pub name: String,
    /// Bumped when the emitted shape changes.
    pub version: u32,
    /// One line, in plain language.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub summary: String,
    /// What makes it fire, and the parameters for that kind.
    #[serde(flatten)]
    pub source: TriggerSource,
    /// The shape of the packet this trigger produces when it fires. `ptn plan`
    /// checks it against the input of every task wired `on:` this trigger.
    pub emits: TypeRef,
}

impl Trigger {
    /// The trigger's own `name@version`.
    pub fn type_ref(&self) -> TypeRef {
        TypeRef::new(self.name.clone(), self.version)
    }
}

/// Which connector kind backs a resource (spec §4).
///
/// `imap`, `mcp` and `memory` are deferred (spec §11) and deliberately absent.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "connector", rename_all = "snake_case")]
pub enum Connector {
    /// A SQL database. Grant scope is a row filter.
    Postgres,
    /// A blob store. Grant scope is a key prefix.
    S3,
    /// An HTTP service. Grant scope is a URL allowlist.
    Http,
}

/// Something persistent the system reaches through the proxy (spec §4).
///
/// Connection config lives here; secrets live executor-side only and never
/// appear in a definition.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Resource {
    /// The logical name a task's `uses:` refers to.
    pub name: String,
    /// Bumped when the exposed verbs change.
    pub version: u32,
    /// One line, in plain language.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub summary: String,
    /// Which connector kind backs this resource.
    #[serde(flatten)]
    pub connector: Connector,
    /// Verbs this resource exposes. A task may only `use` verbs listed here,
    /// and `ptn plan` rejects one that asks for more.
    pub verbs: Vec<String>,
}

impl Resource {
    /// The resource's own `name@version`.
    pub fn type_ref(&self) -> TypeRef {
        TypeRef::new(self.name.clone(), self.version)
    }
}

/// A stochastic body's configuration (spec §4, a value rather than a node).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct AgentSpec {
    /// Dotted identifier, e.g. `report.triage`.
    pub name: String,
    /// Bumped when instructions or output shape change.
    pub version: u32,
    /// Model identifier. Recorded in the run log as audit metadata.
    pub model: String,
    /// The system prompt. Versioned with the spec, so a change is auditable.
    pub instructions: String,
    /// Proxied capabilities this agent may call.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tools: Vec<String>,
    /// Ref of the schema the agent's output is validated against.
    pub output: TypeRef,
    /// Validation failures allowed before a typed failure enters the run log.
    /// Spec §6 caps the repair loop at two attempts.
    #[serde(default = "default_repair_budget")]
    pub repair_budget: u32,
}

fn default_repair_budget() -> u32 {
    2
}

impl AgentSpec {
    /// The spec's own `name@version`.
    pub fn type_ref(&self) -> TypeRef {
        TypeRef::new(self.name.clone(), self.version)
    }
}

/// A registered Record schema (spec §6).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct SchemaDef {
    /// Dotted identifier, e.g. `finance.LedgerQuery`.
    pub name: String,
    /// Bumped when the document changes incompatibly.
    pub version: u32,
    /// The JSON Schema document itself.
    pub document: serde_json::Value,
    /// Nullable now, checking deferred (spec §6). The column exists so that
    /// adding refinement checking later is a feature rather than a migration of
    /// data nobody recorded.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub refines: Option<TypeRef>,
}

impl SchemaDef {
    /// The schema's own `name@version`.
    pub fn type_ref(&self) -> TypeRef {
        TypeRef::new(self.name.clone(), self.version)
    }
}

/// Anything a definition file can declare.
///
/// The `kind:` tag is the discriminator a YAML author writes and the enum arm
/// the executor matches -- one vocabulary, two spellings of it.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Definition {
    /// A unit of work.
    Task(Task),
    /// A declared way for runs to begin.
    Trigger(Trigger),
    /// A connection to something persistent, reached only through the proxy.
    Resource(Resource),
    /// Configuration for a stochastic body.
    AgentSpec(AgentSpec),
    /// A registered Record schema. Business meaning lives here and nowhere else.
    Schema(SchemaDef),
}

impl Definition {
    /// The `kind:` discriminator this definition serialises with.
    pub fn kind(&self) -> &'static str {
        match self {
            Definition::Task(_) => "task",
            Definition::Trigger(_) => "trigger",
            Definition::Resource(_) => "resource",
            Definition::AgentSpec(_) => "agent_spec",
            Definition::Schema(_) => "schema",
        }
    }

    /// The definition's own `name@version`.
    pub fn type_ref(&self) -> TypeRef {
        match self {
            Definition::Task(t) => t.type_ref(),
            Definition::Trigger(t) => t.type_ref(),
            Definition::Resource(r) => r.type_ref(),
            Definition::AgentSpec(a) => a.type_ref(),
            Definition::Schema(s) => s.type_ref(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_go_emitted_task_parses() {
        // Byte-for-byte what pantheon-go's emitter writes today.
        let yaml = r#"
kind: task
name: finance.match_receipts
version: 1
summary: "Find ledger entries with no receipt, and receipts with no ledger entry."

runner:
  kind: script
  runtime: go
  entry: finance.match_receipts

input: finance.ReceiptMatchRequest@1
output: finance.ReceiptMatchReport@1

uses:
  - name: receipts
    verbs: [get, list]

policy:
  timeout: "2m0s"
  retry: 2
  idempotent: true
"#;
        let def: Definition = serde_norway::from_str(yaml).unwrap();
        let Definition::Task(t) = def else {
            panic!("parsed as {}", def.kind());
        };
        assert_eq!(t.name, "finance.match_receipts");
        assert_eq!(t.input.to_string(), "finance.ReceiptMatchRequest@1");
        assert_eq!(t.policy.timeout.as_duration().as_secs(), 120);
        assert_eq!(t.uses.len(), 1);
        assert_eq!(t.uses[0].verbs, vec!["get", "list"]);
        // A generated task declares no wiring: edges are authored separately.
        assert!(t.on.is_none());
        assert!(t.then.is_empty());
    }

    #[test]
    fn a_hand_authored_wiring_task_parses() {
        let yaml = r#"
kind: task
name: report.entry
version: 1
runner: {kind: script, runtime: go, entry: report.entry}
input: report.Request@1
output: report.Spec@1
policy: {timeout: "30s", retry: 0, idempotent: false}
on: report.request@1
then: [report.render@1]
"#;
        let Definition::Task(t) = serde_norway::from_str::<Definition>(yaml).unwrap() else {
            panic!("not a task");
        };
        assert_eq!(t.on.unwrap().to_string(), "report.request@1");
        assert_eq!(t.then[0].to_string(), "report.render@1");
    }

    #[test]
    fn an_unknown_kind_is_refused() {
        let yaml = "kind: dashboard\nname: x\nversion: 1\n";
        assert!(serde_norway::from_str::<Definition>(yaml).is_err());
    }

    #[test]
    fn a_deferred_connector_is_refused() {
        // imap/mcp/memory are deferred (spec §11). Refusing them at parse time
        // is what stops a definition that plans cleanly and cannot run.
        let yaml = "kind: resource\nname: mail\nversion: 1\nconnector: imap\nverbs: [fetch]\n";
        assert!(serde_norway::from_str::<Definition>(yaml).is_err());
    }

    #[test]
    fn a_deferred_trigger_source_is_refused() {
        let yaml = "kind: trigger\nname: t\nversion: 1\nsource: file_watch\npath: /x\nemits: T@1\n";
        assert!(serde_norway::from_str::<Definition>(yaml).is_err());
    }

    #[test]
    fn a_deferred_runner_kind_is_refused() {
        // The `model` runner is deferred (spec §11).
        let yaml = r#"
kind: task
name: t
version: 1
runner: {kind: model, mode: classify}
input: A@1
output: B@1
policy: {timeout: "1s"}
"#;
        assert!(serde_norway::from_str::<Definition>(yaml).is_err());
    }

    #[test]
    fn trigger_sources_flatten() {
        let yaml = "kind: trigger\nname: report.request\nversion: 1\nsource: webhook\npath: /report\nemits: report.Request@1\n";
        let Definition::Trigger(t) = serde_norway::from_str::<Definition>(yaml).unwrap() else {
            panic!("not a trigger");
        };
        assert_eq!(
            t.source,
            TriggerSource::Webhook {
                path: "/report".into()
            }
        );
        assert_eq!(t.emits.to_string(), "report.Request@1");
    }

    #[test]
    fn an_agent_runner_parses_and_defaults_its_repair_budget() {
        let yaml = r#"
kind: agent_spec
name: report.triage
version: 1
model: claude-opus-5
instructions: Summarise the findings.
output: report.Spec@1
"#;
        let Definition::AgentSpec(a) = serde_norway::from_str::<Definition>(yaml).unwrap() else {
            panic!("not an agent spec");
        };
        // Spec §6 caps the repair loop at two attempts; that is the default,
        // not something every author has to remember to write.
        assert_eq!(a.repair_budget, 2);
        assert!(a.tools.is_empty());
    }

    #[test]
    fn every_definition_kind_reports_its_own_ref() {
        let yaml =
            "kind: resource\nname: ledger\nversion: 3\nconnector: postgres\nverbs: [query]\n";
        let def: Definition = serde_norway::from_str(yaml).unwrap();
        assert_eq!(def.kind(), "resource");
        assert_eq!(def.type_ref().to_string(), "ledger@3");
    }

    #[test]
    fn a_task_round_trips_through_yaml() {
        // The registry writes definitions back out; a field that survives
        // parsing but not emitting would corrupt on the second apply.
        let yaml = r#"
kind: task
name: demo.t
version: 2
runner: {kind: script, runtime: go, entry: demo.t}
input: A@1
output: B@1
uses: [{name: db, verbs: [query]}]
policy: {timeout: "45s", retry: 1, idempotent: true}
on: demo.hook@1
then: [demo.next@1]
gate: {approvers: [alice], timeout: "24h0m0s"}
"#;
        let def: Definition = serde_norway::from_str(yaml).unwrap();
        let round: Definition =
            serde_json::from_str(&serde_json::to_string(&def).unwrap()).unwrap();
        assert_eq!(def, round);
    }
}
