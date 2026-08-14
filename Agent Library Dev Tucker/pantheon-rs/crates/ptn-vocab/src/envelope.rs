//! The envelope that accompanies every value crossing a seam (spec §6).

use chrono::{DateTime, SecondsFormat, Utc};
use schemars::JsonSchema;
use serde::{Deserialize, Deserializer, Serialize, Serializer};

use crate::typeref::TypeRef;

/// What an attempt cost.
///
/// `tokens` is always zero for a script runner and non-zero only for an agent
/// runner. It is carried regardless so both runner kinds produce the same
/// envelope shape and downstream readers need no special case.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct BudgetSpent {
    /// Always zero for a script runner; non-zero only for an agent.
    #[serde(default)]
    pub tokens: i64,
    /// Wall time the attempt took.
    #[serde(default)]
    pub ms: i64,
}

/// A mark that a value was influenced by an untrusted source.
///
/// Spec §6: taint is RECORDED AND LOGGED, NOT ENFORCED in v0. Nothing refuses
/// an operation because of a mark. Recording it now is what makes enforcing it
/// later a change of policy rather than a retrofit of provenance nobody kept.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Taint {
    /// What influenced the value, e.g. `resource:crm` or `agent:triage@2`.
    pub source: String,
    /// Why it counts as tainted. Free text, for the audit reader.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub reason: String,
}

/// Accompanies every value crossing a seam.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Envelope {
    /// The run this value belongs to.
    pub run_id: String,
    /// The task instance that produced or received it.
    pub task_id: String,
    /// 1-based. Increments on retry and on agent repair.
    pub attempt: u32,
    /// What the accompanying value actually is. An Error carries
    /// `kernel.Error@1`, not the task's declared output.
    pub schema: TypeRef,
    /// The task ref that produced this, e.g. `finance.fetch_ledger@1`.
    pub producer: String,
    /// `run_events.seq` of the event that caused this.
    pub caused_by: i64,
    /// Always serialised, as `[]` when empty rather than `null`. Spec §6 shows
    /// `taint: []`, and a reader that must handle both null and array for the
    /// same "nothing here" is a reader that will eventually handle one wrong.
    #[serde(default)]
    pub taint: Vec<Taint>,
    #[serde(default)]
    /// What this attempt cost.
    pub budget_spent: BudgetSpent,
    /// When the value was produced, RFC 3339 with a `Z` suffix.
    // schemars needs telling what the custom serde impl produces; it cannot
    // infer a shape from a module path.
    #[serde(with = "rfc3339")]
    #[schemars(with = "String")]
    pub ts: DateTime<Utc>,
}

impl Envelope {
    /// Builds the outbound envelope for a result produced from this inbound one.
    ///
    /// Taint is carried forward, never dropped. Laundering provenance through
    /// an aggregation is the exact failure mode recording taint exists to make
    /// visible.
    pub fn derive(
        &self,
        schema: TypeRef,
        producer: impl Into<String>,
        spent: BudgetSpent,
        now: DateTime<Utc>,
    ) -> Envelope {
        Envelope {
            schema,
            producer: producer.into(),
            budget_spent: spent,
            ts: now,
            taint: self.taint.clone(),
            ..self.clone()
        }
    }

    /// Returns a copy carrying one more mark, skipping exact duplicates.
    ///
    /// A loop over 10,000 rows from one tainted resource should leave one mark,
    /// not ten thousand.
    pub fn with_taint(&self, t: Taint) -> Envelope {
        let mut out = self.clone();
        if !out.taint.contains(&t) {
            out.taint.push(t);
        }
        out
    }
}

/// RFC 3339 with a `Z` suffix, matching Go's `time.Time` JSON encoding.
///
/// chrono's default impl emits `+00:00` for UTC. Go emits `Z`. Both are valid
/// RFC 3339 and neither is wrong, which is precisely why it has to be pinned:
/// two runners disagreeing on a timestamp's spelling produces envelopes that
/// compare unequal while meaning the same instant.
mod rfc3339 {
    use super::*;

    pub fn serialize<S: Serializer>(ts: &DateTime<Utc>, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&ts.to_rfc3339_opts(SecondsFormat::Secs, true))
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<DateTime<Utc>, D::Error> {
        let s = String::deserialize(d)?;
        DateTime::parse_from_rfc3339(&s)
            .map(|t| t.with_timezone(&Utc))
            .map_err(serde::de::Error::custom)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn at(secs: i64) -> DateTime<Utc> {
        Utc.timestamp_opt(secs, 0).unwrap()
    }

    fn envelope() -> Envelope {
        Envelope {
            run_id: "r-1".into(),
            task_id: "t-1".into(),
            attempt: 2,
            schema: TypeRef::new("In", 1),
            producer: "p".into(),
            caused_by: 7,
            taint: vec![],
            budget_spent: BudgetSpent::default(),
            ts: at(0),
        }
    }

    #[test]
    fn empty_taint_serialises_as_an_array_not_null() {
        let json = serde_json::to_value(envelope()).unwrap();
        assert_eq!(json["taint"], serde_json::json!([]));
    }

    #[test]
    fn timestamps_use_a_z_suffix() {
        let json = serde_json::to_value(envelope()).unwrap();
        assert_eq!(json["ts"], "1970-01-01T00:00:00Z");
    }

    #[test]
    fn derive_carries_taint_and_causal_fields() {
        let inbound = envelope().with_taint(Taint {
            source: "resource:crm".into(),
            reason: String::new(),
        });
        let out = inbound.derive(
            TypeRef::new("Out", 1),
            "producer",
            BudgetSpent { tokens: 0, ms: 5 },
            at(10),
        );

        assert_eq!(out.taint.len(), 1, "taint was dropped across derive");
        assert_eq!(out.run_id, "r-1");
        assert_eq!(out.task_id, "t-1");
        assert_eq!(out.attempt, 2);
        assert_eq!(out.caused_by, 7);
        assert_eq!(out.schema.name, "Out");
        assert_eq!(out.producer, "producer");
    }

    #[test]
    fn with_taint_deduplicates() {
        let mut e = envelope();
        for _ in 0..100 {
            e = e.with_taint(Taint {
                source: "resource:ledger".into(),
                reason: "query".into(),
            });
        }
        assert_eq!(e.taint.len(), 1);
    }
}
