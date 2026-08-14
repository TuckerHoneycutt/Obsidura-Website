//! The kernel `Value`: a closed set of five variants (spec §5).
//!
//! This is the vocabulary the executor has operational duties toward, and
//! nothing else. Store, hash and gate Files; meter Tables; validate Records
//! against their registered schema; route Errors. Everything with business
//! *meaning* is a `Record`, and the executor's entire relationship with one is
//! `validate(schema, data)`.
//!
//! Adding a variant here is a change to the executor, which is exactly the
//! coupling invariant 1 forbids growing. If a new business concept seems to
//! need a variant, it is a Record.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use crate::typeref::TypeRef;

/// A body of prose.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Text {
    /// The prose itself.
    pub body: String,
    /// BCP 47 tag. Absent means unstated, not English.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lang: Option<String>,
}

/// A content-addressed blob reference.
///
/// Bodies never construct one: the hash is the executor's to compute and trust.
/// Spec §5 folds Bin into File, so `media_type` is what distinguishes a PDF
/// from an HTML report from an mdzip — and understanding it is an action's job
/// at the edge, never the executor's.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct FileHandle {
    /// Content address, `sha256:<hex>`. The executor computes it; a body never does.
    pub blob: String,
    /// What the bytes are. Spec §5 folds Bin into File, so this is the only
    /// thing distinguishing a PDF from an HTML report.
    pub media_type: String,
    /// Bytes. Omitted when zero.
    #[serde(default, skip_serializing_if = "is_zero_u64")]
    pub size: u64,
    /// Grants the holder read access to this blob for the run's lifetime.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub capability: String,
    /// Suggested name for a download. Advisory only.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub filename: String,
}

/// One column's metadata in a table.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Column {
    /// Column name. Rows are addressed by this, never by position.
    pub name: String,
    /// `string` | `int` | `float` | `bool` | `timestamp`.
    /// One of `string`, `int`, `float`, `bool`, `timestamp`.
    #[serde(rename = "type")]
    pub column_type: String,
}

/// Column metadata plus a blob-store row source.
///
/// CSV/JSONL in v0; Arrow is deferred (spec §11). Rows are read in chunks
/// through the proxy so access stays metered and memory stays bounded.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct TableHandle {
    /// Content address, `sha256:<hex>`. The executor computes it; a body never does.
    pub blob: String,
    /// `csv` or `jsonl` in v0. Arrow is deferred (spec §11).
    pub format: String,
    /// Declared, never inferred: inferring from row one makes a column of
    /// integers become a column of strings the day row one is null.
    pub columns: Vec<Column>,
    /// Advisory row count; zero when unknown.
    /// Advisory row count. Zero means unknown, not empty.
    #[serde(default, skip_serializing_if = "is_zero_u64")]
    pub rows: u64,
    /// Grants the holder read access to this blob for the run's lifetime.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub capability: String,
}

/// A typed failure that flows as a value.
///
/// A business failure is a Value the run log routes; a protocol fault is not.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct ErrorValue {
    /// Stable, machine-readable failure class, e.g. `timeout`.
    pub code: String,
    /// Human-readable explanation.
    pub message: String,
    /// Structured context for whoever debugs this.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub detail: Option<serde_json::Value>,
    /// Whether retrying could plausibly succeed. Advisory to the executor.
    #[serde(default, skip_serializing_if = "is_false")]
    pub retry: bool,
}

/// The kernel's closed set of five (spec §5).
///
/// Internally tagged, so each variant's fields sit alongside `"kind"` in the
/// serialised object. That representation is the contract every runner
/// implementation shares; `tests/wire_compat.rs` pins it against a corpus the
/// Go runner reads too.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Value {
    /// Prose. Human-facing output that is not a document.
    Text(Text),
    /// Stored bytes by content address. Any media type, including binary.
    File(FileHandle),
    /// Stored rows by handle, read in chunks so size stays bounded.
    Table(TableHandle),
    /// Carries all business meaning. The executor's entire relationship with
    /// one is `validate(schema, data)`, which is what keeps the amount of Rust
    /// in the executor constant in the number of business types (invariant 1).
    Record {
        /// Which registered schema `data` must validate against.
        type_ref: TypeRef,
        /// The business payload. Opaque to the executor.
        data: serde_json::Value,
    },
    /// A typed failure. Routed by the executor, not raised as a fault.
    Error(ErrorValue),
}

impl Value {
    /// The discriminator this value serialises with.
    pub fn kind(&self) -> &'static str {
        match self {
            Value::Text(_) => "text",
            Value::File(_) => "file",
            Value::Table(_) => "table",
            Value::Record { .. } => "record",
            Value::Error(_) => "error",
        }
    }

    /// A `Text` value with no language tag.
    pub fn text(body: impl Into<String>) -> Self {
        Value::Text(Text {
            body: body.into(),
            lang: None,
        })
    }

    /// A `Record` carrying already-serialised data.
    pub fn record(type_ref: TypeRef, data: serde_json::Value) -> Self {
        Value::Record { type_ref, data }
    }

    /// A non-retryable `Error` with no structured detail.
    pub fn error(code: impl Into<String>, message: impl Into<String>) -> Self {
        Value::Error(ErrorValue {
            code: code.into(),
            message: message.into(),
            detail: None,
            retry: false,
        })
    }

    /// The schema a produced value actually carries.
    ///
    /// An Error is a kernel value, not the task's declared output type.
    /// Labelling a failure with the success schema would make the run log lie.
    pub fn schema_ref(&self) -> TypeRef {
        match self {
            Value::Record { type_ref, .. } => type_ref.clone(),
            Value::Text(_) => TypeRef::new("kernel.Text", 1),
            Value::File(_) => TypeRef::new("kernel.File", 1),
            Value::Table(_) => TypeRef::new("kernel.Table", 1),
            Value::Error(_) => TypeRef::new("kernel.Error", 1),
        }
    }
}

fn is_zero_u64(v: &u64) -> bool {
    *v == 0
}

fn is_false(v: &bool) -> bool {
    !*v
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn is_internally_tagged() {
        let v = Value::text("hello");
        let got = serde_json::to_value(&v).unwrap();
        // Fields sit alongside "kind", not nested under it.
        assert_eq!(got, json!({"kind": "text", "body": "hello"}));
    }

    #[test]
    fn every_variant_round_trips() {
        let values = vec![
            Value::text("hi"),
            Value::File(FileHandle {
                blob: "sha256:ab".into(),
                media_type: "application/pdf".into(),
                size: 12,
                capability: String::new(),
                filename: String::new(),
            }),
            Value::Table(TableHandle {
                blob: "sha256:cd".into(),
                format: "csv".into(),
                columns: vec![Column {
                    name: "a".into(),
                    column_type: "int".into(),
                }],
                rows: 0,
                capability: String::new(),
            }),
            Value::record(TypeRef::new("Invoice", 2), json!({"total": 12.5})),
            Value::error("bad_input", "nope"),
        ];
        for v in values {
            let s = serde_json::to_string(&v).unwrap();
            let back: Value = serde_json::from_str(&s).unwrap();
            assert_eq!(v, back, "round trip changed {}", v.kind());
        }
    }

    /// The kernel is a closed set of five. A runner that skipped an
    /// unrecognised variant would hand downstream tasks nothing, and the
    /// failure would surface far from its cause.
    #[test]
    fn unknown_kind_is_refused() {
        let err = serde_json::from_str::<Value>(r#"{"kind":"quaternion","spin":2}"#);
        assert!(err.is_err());
    }

    #[test]
    fn missing_kind_is_refused() {
        assert!(serde_json::from_str::<Value>(r#"{"body":"hi"}"#).is_err());
    }

    #[test]
    fn empty_optionals_are_omitted() {
        // Matching the Go runner's omitempty rules is what keeps one corpus
        // valid for both implementations.
        let v = Value::File(FileHandle {
            blob: "sha256:ab".into(),
            media_type: "text/html".into(),
            size: 0,
            capability: String::new(),
            filename: String::new(),
        });
        let got = serde_json::to_value(&v).unwrap();
        assert_eq!(
            got,
            json!({"kind":"file","blob":"sha256:ab","media_type":"text/html"})
        );
    }

    #[test]
    fn an_error_is_labelled_as_an_error_not_as_the_success_type() {
        assert_eq!(Value::error("e", "m").schema_ref().name, "kernel.Error");
    }
}
