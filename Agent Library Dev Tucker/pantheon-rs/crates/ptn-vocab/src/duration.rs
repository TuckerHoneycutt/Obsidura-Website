//! Go-style duration strings, because that is what the definitions carry.

use std::fmt;
use std::str::FromStr;
use std::time::Duration;

use schemars::JsonSchema;
use serde::{de, Deserialize, Deserializer, Serialize, Serializer};

/// A duration spelled the way Go spells it: `2m0s`, `1h30m`, `500ms`.
///
/// Quoted in YAML and parsed here rather than left as a bare scalar. A bare
/// `1:30` is sexagesimal to a YAML 1.1 reader and a string to a YAML 1.2 one,
/// and a timeout that means ninety seconds to one parser and ninety minutes to
/// another is the kind of disagreement nobody finds until production.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, PartialOrd, Ord)]
pub struct GoDuration(pub Duration);

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
/// Why a duration string could not be parsed.
pub enum DurationError {
    /// The string was blank.
    #[error("duration {0:?} is empty")]
    Empty(String),
    /// A bare number, e.g. `60`. Seconds? Minutes? Refused rather than guessed.
    #[error("duration {0:?} has no unit; write 60s, not 60")]
    NoUnit(String),
    /// A unit outside `ns|us|ms|s|m|h`.
    #[error("duration {0:?} has an unknown unit {1:?}")]
    BadUnit(String, String),
    /// Not a number-then-unit sequence.
    #[error("duration {0:?} is not a number followed by a unit")]
    Malformed(String),
}

impl GoDuration {
    /// Builds a duration of whole seconds.
    pub fn from_secs(s: u64) -> Self {
        GoDuration(Duration::from_secs(s))
    }

    /// The underlying `std::time::Duration`.
    pub fn as_duration(self) -> Duration {
        self.0
    }

    /// True for a zero-length duration.
    pub fn is_zero(&self) -> bool {
        self.0.is_zero()
    }
}

impl FromStr for GoDuration {
    type Err = DurationError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let raw = s.trim();
        if raw.is_empty() {
            return Err(DurationError::Empty(s.to_owned()));
        }
        if raw == "0" {
            return Ok(GoDuration(Duration::ZERO));
        }

        let mut total = Duration::ZERO;
        let mut rest = raw;
        let mut saw_any = false;

        while !rest.is_empty() {
            let num_end = rest
                .find(|c: char| !c.is_ascii_digit() && c != '.')
                .ok_or_else(|| DurationError::NoUnit(s.to_owned()))?;
            if num_end == 0 {
                return Err(DurationError::Malformed(s.to_owned()));
            }
            let value: f64 = rest[..num_end]
                .parse()
                .map_err(|_| DurationError::Malformed(s.to_owned()))?;
            rest = &rest[num_end..];

            let unit_end = rest
                .find(|c: char| c.is_ascii_digit())
                .unwrap_or(rest.len());
            let unit = &rest[..unit_end];
            rest = &rest[unit_end..];

            let nanos = match unit {
                "ns" => 1.0,
                "us" | "µs" => 1e3,
                "ms" => 1e6,
                "s" => 1e9,
                "m" => 60e9,
                "h" => 3600e9,
                other => return Err(DurationError::BadUnit(s.to_owned(), other.to_owned())),
            };
            total += Duration::from_nanos((value * nanos) as u64);
            saw_any = true;
        }

        if !saw_any {
            return Err(DurationError::NoUnit(s.to_owned()));
        }
        Ok(GoDuration(total))
    }
}

impl fmt::Display for GoDuration {
    /// Renders the way Go's `Duration.String` does, so a definition
    /// round-trips through `ptn plan` byte-for-byte and the drift gate on the
    /// generating side stays quiet.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let d = self.0;
        if d.is_zero() {
            return write!(f, "0s");
        }
        let nanos = d.as_nanos();

        if nanos < 1_000 {
            return write!(f, "{nanos}ns");
        }
        if nanos < 1_000_000 {
            return write!(f, "{}µs", trim_float(nanos as f64 / 1e3));
        }
        if nanos < 1_000_000_000 {
            return write!(f, "{}ms", trim_float(nanos as f64 / 1e6));
        }

        let total_secs = d.as_secs();
        let frac = d.subsec_nanos();
        let hours = total_secs / 3600;
        let minutes = (total_secs % 3600) / 60;
        let secs = total_secs % 60;

        let secs_str = if frac == 0 {
            format!("{secs}s")
        } else {
            format!("{}s", trim_float(secs as f64 + frac as f64 / 1e9))
        };

        if hours > 0 {
            write!(f, "{hours}h{minutes}m{secs_str}")
        } else if minutes > 0 {
            write!(f, "{minutes}m{secs_str}")
        } else {
            write!(f, "{secs_str}")
        }
    }
}

fn trim_float(v: f64) -> String {
    let s = format!("{v:.9}");
    let s = s.trim_end_matches('0').trim_end_matches('.');
    s.to_owned()
}

impl Serialize for GoDuration {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for GoDuration {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let s = String::deserialize(d)?;
        s.parse().map_err(de::Error::custom)
    }
}

impl JsonSchema for GoDuration {
    fn schema_name() -> std::borrow::Cow<'static, str> {
        "Duration".into()
    }

    fn json_schema(_: &mut schemars::SchemaGenerator) -> schemars::Schema {
        schemars::json_schema!({
            "type": "string",
            "description": "Duration with an explicit unit, e.g. 30s, 2m0s, 1h30m.",
            "pattern": r"^(\d+(\.\d+)?(ns|us|µs|ms|s|m|h))+$",
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_what_the_emitter_writes() {
        // Exactly the spellings pantheon-go's emitter produces today.
        for (input, secs) in [("30s", 30u64), ("1m0s", 60), ("2m0s", 120), ("5m0s", 300)] {
            let d: GoDuration = input.parse().unwrap();
            assert_eq!(d.0.as_secs(), secs, "{input}");
        }
    }

    #[test]
    fn round_trips_through_display() {
        for input in ["30s", "1m0s", "2m0s", "1h30m0s", "500ms", "0s"] {
            let d: GoDuration = input.parse().unwrap();
            assert_eq!(d.to_string(), input, "{input} did not round-trip");
        }
    }

    #[test]
    fn a_bare_number_is_refused() {
        // "60" could mean seconds, minutes or nanoseconds depending on who is
        // reading. Refusing it is cheaper than guessing wrong.
        assert!("60".parse::<GoDuration>().is_err());
        assert!("".parse::<GoDuration>().is_err());
        assert!("60x".parse::<GoDuration>().is_err());
    }

    #[test]
    fn compound_durations_add_up() {
        let d: GoDuration = "1h30m".parse().unwrap();
        assert_eq!(d.0.as_secs(), 5400);
    }
}
