#![warn(missing_docs)]

//! Pantheon's kernel vocabulary — chunk 1 of the P0 build plan.
//!
//! **This crate is the source of truth for the wire format.** Spec §4 makes
//! Rust the vocabulary's home, with JSON Schema generated from these types via
//! schemars and every other implementation generated from that schema in turn.
//!
//! The Go runner in `pantheon-go/` currently hand-writes its mirror of these
//! types, because this crate did not exist when it was written. That arrow is
//! backwards and temporary. `tests/wire_compat.rs` holds the two ends together
//! in the meantime: both implementations round-trip one shared corpus, so
//! divergence is a failing test rather than a wrong number in a report.
//!
//! What belongs here: the closed set of five kernel values, the envelope, and
//! the definition primitives. What does not: anything with business meaning.
//! Invoices, patients and telemetry are `Record`s, and this crate's entire
//! relationship with one is `validate(schema, data)` — which is what keeps the
//! amount of Rust constant in the number of business types (invariant 1).

pub mod duration;
pub mod envelope;
pub mod primitives;
pub mod typeref;
pub mod value;

pub use duration::GoDuration;
pub use envelope::{BudgetSpent, Envelope, Taint};
pub use primitives::{
    AgentSpec, ApprovalGate, Connector, Definition, Policy, Resource, ResourceUse, Runner,
    SchemaDef, Task, Trigger, TriggerSource,
};
pub use typeref::{TypeRef, TypeRefError};
pub use value::{Column, ErrorValue, FileHandle, TableHandle, Text, Value};

/// Protocol and kernel versions this build speaks.
///
/// A mismatch is refused at the runner handshake rather than tolerated. An SDK
/// built for kernel v1 talking to an executor on kernel v2 misreads envelopes
/// and emits plausible wrong output, which is the most expensive failure this
/// system can have.
/// Version of the runner protocol (see `pantheon-go/PROTOCOL.md`).
pub const PROTOCOL_VERSION: u32 = 1;
/// Version of the kernel vocabulary defined by this crate.
pub const KERNEL_VERSION: u32 = 1;

/// Emits the JSON Schema for every vocabulary type.
///
/// This is the artifact other implementations generate from. It is also what a
/// reviewer diffs when a type changes: a vocabulary change is a wire change,
/// and a wire change should be visible as one.
pub fn schemas() -> serde_json::Value {
    use schemars::schema_for;
    serde_json::json!({
        "kernel_version": KERNEL_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "definitions": {
            "Value": schema_for!(Value),
            "Envelope": schema_for!(Envelope),
            "Definition": schema_for!(Definition),
            "Task": schema_for!(Task),
            "Trigger": schema_for!(Trigger),
            "Resource": schema_for!(Resource),
            "AgentSpec": schema_for!(AgentSpec),
            "SchemaDef": schema_for!(SchemaDef),
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn schema_emission_covers_every_kernel_kind() {
        let s = schemas();
        let value_schema = serde_json::to_string(&s["definitions"]["Value"]).unwrap();
        for kind in ["text", "file", "table", "record", "error"] {
            assert!(
                value_schema.contains(kind),
                "the emitted Value schema does not mention the {kind} variant"
            );
        }
    }

    #[test]
    fn schema_emission_is_stable() {
        // Reviewers diff this output; it must not reorder between runs.
        assert_eq!(
            serde_json::to_string(&schemas()).unwrap(),
            serde_json::to_string(&schemas()).unwrap()
        );
    }
}
