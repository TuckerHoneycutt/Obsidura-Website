//! Schema references, spelled `name@version`.

use std::fmt;
use std::str::FromStr;

use schemars::JsonSchema;
use serde::{de, Deserialize, Deserializer, Serialize, Serializer};

/// Names a registered schema as `name@version` (spec §6).
///
/// The default `TypeRef` is empty and serialises as `""`. That is deliberate:
/// a wire type must round-trip its own default, or every optional ref becomes a
/// decode failure somewhere far from the omission. "A schema is required here"
/// is a validation rule the registry enforces, not a parsing rule.
#[derive(Debug, Clone, Default, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct TypeRef {
    /// Dotted schema name, e.g. `finance.LedgerQuery`.
    pub name: String,
    /// Positive integer. Version 0 is never valid.
    pub version: u32,
}

/// Why a type ref could not be parsed.
#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum TypeRefError {
    /// The string had no `@`, or nothing on one side of it.
    #[error("type ref {0:?} is not name@version")]
    Malformed(String),
    /// The part after `@` was not a positive integer.
    #[error("type ref {0:?} has a non-positive-integer version")]
    BadVersion(String),
}

impl TypeRef {
    /// Builds a ref. The version is not validated here; parsing is where
    /// strictness lives.
    pub fn new(name: impl Into<String>, version: u32) -> Self {
        Self {
            name: name.into(),
            version,
        }
    }

    /// True for the default, empty ref.
    pub fn is_empty(&self) -> bool {
        self.name.is_empty() && self.version == 0
    }
}

impl FromStr for TypeRef {
    type Err = TypeRefError;

    /// Strict: a bare name is an error rather than an implied version 1.
    /// An implied version is a pin that silently moves the day a second
    /// version is registered.
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let at = s
            .rfind('@')
            .ok_or_else(|| TypeRefError::Malformed(s.to_owned()))?;
        if at == 0 || at + 1 == s.len() {
            return Err(TypeRefError::Malformed(s.to_owned()));
        }
        let version: u32 = s[at + 1..]
            .parse()
            .map_err(|_| TypeRefError::BadVersion(s.to_owned()))?;
        if version < 1 {
            return Err(TypeRefError::BadVersion(s.to_owned()));
        }
        Ok(Self {
            name: s[..at].to_owned(),
            version,
        })
    }
}

impl fmt::Display for TypeRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.name.is_empty() {
            return Ok(());
        }
        write!(f, "{}@{}", self.name, self.version)
    }
}

impl Serialize for TypeRef {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for TypeRef {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let s = String::deserialize(d)?;
        if s.is_empty() {
            return Ok(Self::default());
        }
        s.parse().map_err(de::Error::custom)
    }
}

impl JsonSchema for TypeRef {
    fn schema_name() -> std::borrow::Cow<'static, str> {
        "TypeRef".into()
    }

    fn json_schema(_: &mut schemars::SchemaGenerator) -> schemars::Schema {
        schemars::json_schema!({
            "type": "string",
            "description": "Schema reference, spelled name@version. Empty means unset.",
            "pattern": r"^$|^.+@[1-9][0-9]*$",
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_name_and_version() {
        let r: TypeRef = "finance.LedgerQuery@2".parse().unwrap();
        assert_eq!(r.name, "finance.LedgerQuery");
        assert_eq!(r.version, 2);
        assert_eq!(r.to_string(), "finance.LedgerQuery@2");
    }

    #[test]
    fn refuses_an_implied_version() {
        // An implied version is a pin that silently moves.
        assert!("Invoice".parse::<TypeRef>().is_err());
        assert!("Invoice@".parse::<TypeRef>().is_err());
        assert!("@1".parse::<TypeRef>().is_err());
        assert!("Invoice@0".parse::<TypeRef>().is_err());
        assert!("Invoice@x".parse::<TypeRef>().is_err());
    }

    #[test]
    fn default_round_trips_through_json() {
        let json = serde_json::to_string(&TypeRef::default()).unwrap();
        assert_eq!(json, r#""""#);
        let back: TypeRef = serde_json::from_str(&json).unwrap();
        assert!(back.is_empty());
    }

    #[test]
    fn malformed_refs_are_still_refused_on_the_wire() {
        for bad in [r#""Invoice""#, r#""Invoice@""#, r#""Invoice@0""#] {
            assert!(
                serde_json::from_str::<TypeRef>(bad).is_err(),
                "{bad} was accepted"
            );
        }
    }
}
