package kernel_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"github.com/obsidura/pantheon-go/kernel"
)

// Conformance against the shared wire corpus.
//
// The corpus lives in pantheon-rs/testdata/wire/ and is the contract between
// this package and ptn-vocab, the Rust crate that is the source of truth for
// the vocabulary. Both read the same files and make the same assertion, so a
// disagreement about the wire format is a failing test in one of two places
// rather than a wrong number in a report six weeks later.
//
// Comparison is canonical -- keys sorted, whitespace ignored -- so the corpus
// stays readable. What it does NOT ignore is a field appearing or disappearing,
// which is where cross-language drift actually happens.

const corpusRel = "../../pantheon-rs/testdata/wire"

func corpusDir(t *testing.T) string {
	t.Helper()
	dir, err := filepath.Abs(corpusRel)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(dir); err != nil {
		t.Skipf("wire corpus not present at %s (is pantheon-rs checked out?)", dir)
	}
	return dir
}

// canonical parses and re-emits with sorted keys. Round-tripping through `any`
// is enough: encoding/json sorts map keys on the way out.
func canonical(t *testing.T, raw []byte) string {
	t.Helper()
	var v any
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatalf("corpus file is not valid JSON: %v", err)
	}
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func corpusFiles(t *testing.T) []string {
	t.Helper()
	entries, err := os.ReadDir(corpusDir(t))
	if err != nil {
		t.Fatal(err)
	}
	var names []string
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	return names
}

func TestEveryCorpusFileRoundTripsUnchanged(t *testing.T) {
	dir := corpusDir(t)
	names := corpusFiles(t)
	if len(names) == 0 {
		t.Fatal("the corpus is empty; this test would pass vacuously")
	}

	for _, name := range names {
		t.Run(name, func(t *testing.T) {
			body, err := os.ReadFile(filepath.Join(dir, name))
			if err != nil {
				t.Fatal(err)
			}

			var produced []byte
			switch {
			case strings.HasPrefix(name, "value_"):
				var v kernel.Value
				if err := json.Unmarshal(body, &v); err != nil {
					t.Fatalf("parsing as Value: %v", err)
				}
				if produced, err = json.Marshal(v); err != nil {
					t.Fatal(err)
				}
			case strings.HasPrefix(name, "envelope_"):
				var e kernel.Envelope
				if err := json.Unmarshal(body, &e); err != nil {
					t.Fatalf("parsing as Envelope: %v", err)
				}
				if produced, err = json.Marshal(e); err != nil {
					t.Fatal(err)
				}
			default:
				t.Fatalf("corpus files must be named value_* or envelope_* so the reader knows what parses them")
			}

			want, got := canonical(t, body), canonical(t, produced)
			if want != got {
				t.Errorf("did not round-trip.\n  corpus:   %s\n  produced: %s", want, got)
			}
		})
	}
}

func TestCorpusCoversEveryKernelKind(t *testing.T) {
	dir := corpusDir(t)
	seen := map[kernel.Kind]bool{}
	for _, name := range corpusFiles(t) {
		if !strings.HasPrefix(name, "value_") {
			continue
		}
		body, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			t.Fatal(err)
		}
		var v kernel.Value
		if err := json.Unmarshal(body, &v); err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		seen[v.Kind] = true
	}
	for _, k := range []kernel.Kind{
		kernel.KindText, kernel.KindFile, kernel.KindTable, kernel.KindRecord, kernel.KindError,
	} {
		if !seen[k] {
			t.Errorf("the corpus has no %s example", k)
		}
	}
}

// The two shapes most likely to differ between implementations, asserted
// directly rather than left to the round-trip to catch by luck.
func TestShapesThatActuallyDriftArePinned(t *testing.T) {
	dir := corpusDir(t)

	body, err := os.ReadFile(filepath.Join(dir, "envelope_empty_taint.json"))
	if err != nil {
		t.Fatal(err)
	}
	var e kernel.Envelope
	if err := json.Unmarshal(body, &e); err != nil {
		t.Fatal(err)
	}
	out, err := json.Marshal(e)
	if err != nil {
		t.Fatal(err)
	}
	var m map[string]json.RawMessage
	if err := json.Unmarshal(out, &m); err != nil {
		t.Fatal(err)
	}

	// A nil slice marshals to null in Go and [] in Rust unless someone decides.
	// Spec §6 shows `taint: []`.
	if string(m["taint"]) != "[]" {
		t.Errorf("empty taint marshalled as %s; it must be [] and not null", m["taint"])
	}
	// Go emits Z; chrono defaults to +00:00. Both are valid RFC 3339, which is
	// exactly why it has to be pinned.
	if string(m["ts"]) != `"2026-08-12T09:15:00Z"` {
		t.Errorf("timestamp marshalled as %s", m["ts"])
	}

	// An unset ref must survive as "" rather than failing to parse.
	unset, err := os.ReadFile(filepath.Join(dir, "envelope_unset_schema.json"))
	if err != nil {
		t.Fatal(err)
	}
	var u kernel.Envelope
	if err := json.Unmarshal(unset, &u); err != nil {
		t.Fatalf("an envelope with an unset schema must parse: %v", err)
	}
	if !u.Schema.IsZero() {
		t.Errorf("unset schema parsed as %+v", u.Schema)
	}
}

// A zero Envelope must not emit null for taint either. The corpus catches the
// parsed case; this catches the constructed one, which is what a body actually
// produces.
func TestZeroEnvelopeEmitsEmptyTaintArray(t *testing.T) {
	b, err := json.Marshal(kernel.Envelope{})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(b), `"taint":[]`) {
		t.Errorf("a zero envelope marshalled taint as null: %s", b)
	}
}
