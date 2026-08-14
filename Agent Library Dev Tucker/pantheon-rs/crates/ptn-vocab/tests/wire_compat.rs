//! Conformance against the shared wire corpus.
//!
//! The corpus in `pantheon-rs/testdata/wire/` is the contract between this
//! crate and every other implementation of the vocabulary. The Go runner's
//! `kernel/wire_compat_test.go` reads the same directory and makes the same
//! assertion, so a disagreement about the wire format is a failing test in one
//! of two places rather than a wrong number in a report six weeks later.
//!
//! Comparison is canonical — keys sorted, whitespace ignored — so the corpus
//! files can stay readable. What it does NOT ignore is a field that appears or
//! disappears, which is where cross-language drift actually happens: `null` vs
//! `[]`, an omitted zero, a timestamp spelled `+00:00` instead of `Z`.

use std::fs;
use std::path::{Path, PathBuf};

use ptn_vocab::{Envelope, Value};

fn corpus_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../testdata/wire")
        .canonicalize()
        .expect("wire corpus directory not found")
}

/// Canonical JSON: parsed, keys sorted (serde_json::Value is BTreeMap-backed),
/// re-emitted compact.
fn canonical(raw: &str) -> String {
    let v: serde_json::Value = serde_json::from_str(raw).expect("corpus file is not valid JSON");
    serde_json::to_string(&v).expect("re-serialising canonical form")
}

fn corpus_files() -> Vec<(String, String)> {
    let mut out = Vec::new();
    for entry in fs::read_dir(corpus_dir()).expect("reading corpus") {
        let path = entry.expect("corpus entry").path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        let name = path.file_name().unwrap().to_string_lossy().into_owned();
        let body = fs::read_to_string(&path).expect("reading corpus file");
        out.push((name, body));
    }
    out.sort();
    out
}

#[test]
fn every_corpus_file_round_trips_unchanged() {
    let files = corpus_files();
    assert!(
        !files.is_empty(),
        "the corpus is empty; this test would pass vacuously"
    );

    for (name, body) in &files {
        let produced = if name.starts_with("value_") {
            let v: Value = serde_json::from_str(body)
                .unwrap_or_else(|e| panic!("{name}: parsing as Value: {e}"));
            serde_json::to_string(&v).unwrap()
        } else if name.starts_with("envelope_") {
            let e: Envelope = serde_json::from_str(body)
                .unwrap_or_else(|err| panic!("{name}: parsing as Envelope: {err}"));
            serde_json::to_string(&e).unwrap()
        } else {
            panic!("{name}: corpus files must be named value_* or envelope_* so the reader knows what parses them");
        };

        assert_eq!(
            canonical(&produced),
            canonical(body),
            "\n{name} did not round-trip.\n  corpus:   {}\n  produced: {}\n",
            canonical(body),
            canonical(&produced),
        );
    }
}

/// The corpus must actually exercise every kernel variant, or a variant could
/// drift for a year without anyone noticing.
#[test]
fn the_corpus_covers_every_kernel_kind() {
    let mut seen = std::collections::BTreeSet::new();
    for (name, body) in corpus_files() {
        if !name.starts_with("value_") {
            continue;
        }
        let v: Value = serde_json::from_str(&body).unwrap();
        seen.insert(v.kind());
    }
    for kind in ["text", "file", "table", "record", "error"] {
        assert!(seen.contains(kind), "the corpus has no {kind} example");
    }
}

/// The two shapes most likely to differ between implementations, asserted
/// directly rather than left to the round-trip to catch by luck.
#[test]
fn the_shapes_that_actually_drift_are_pinned() {
    let body = fs::read_to_string(corpus_dir().join("envelope_empty_taint.json")).unwrap();
    let e: Envelope = serde_json::from_str(&body).unwrap();
    let out = serde_json::to_value(&e).unwrap();

    // A nil slice is `null` in Go and `[]` in Rust unless someone decides.
    // Spec §6 shows `taint: []`.
    assert_eq!(
        out["taint"],
        serde_json::json!([]),
        "empty taint must be [] and not null"
    );

    // chrono defaults to `+00:00`; Go emits `Z`. Both are valid RFC 3339,
    // which is exactly why it has to be pinned.
    assert_eq!(out["ts"], "2026-08-12T09:15:00Z");

    // An unset ref must survive as "" rather than failing to parse.
    let unset = fs::read_to_string(corpus_dir().join("envelope_unset_schema.json")).unwrap();
    let e: Envelope = serde_json::from_str(&unset).unwrap();
    assert!(e.schema.is_empty());
    assert_eq!(serde_json::to_value(&e).unwrap()["schema"], "");
}
