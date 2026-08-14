package kernel

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

// The wire format is the contract with a Rust executor and a Python runner
// neither of which exists yet to disagree with us. These tests pin the exact
// bytes, so when the Rust side does appear, disagreement is a failing test
// rather than a subtly wrong envelope in a report.

func TestValueMarshalsInternallyTagged(t *testing.T) {
	cases := []struct {
		name string
		val  Value
		want string
	}{
		{
			"text",
			NewText("hello"),
			`{"body":"hello","kind":"text"}`,
		},
		{
			"file",
			NewFile(FileHandle{Blob: "sha256:ab", MediaType: "text/html", Size: 12}),
			`{"blob":"sha256:ab","kind":"file","media_type":"text/html","size":12}`,
		},
		{
			"error",
			NewError("bad_input", "nope"),
			`{"code":"bad_input","kind":"error","message":"nope"}`,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			b, err := json.Marshal(tc.val)
			if err != nil {
				t.Fatalf("marshal: %v", err)
			}
			if string(b) != tc.want {
				t.Errorf("wire format drifted\n got: %s\nwant: %s", b, tc.want)
			}
		})
	}
}

func TestValueRoundTripsEveryKind(t *testing.T) {
	rec, err := NewRecord(Ref("Invoice", 2), map[string]any{"total": 12.5})
	if err != nil {
		t.Fatal(err)
	}
	vals := []Value{
		NewText("hi"),
		NewFile(FileHandle{Blob: "sha256:x", MediaType: "application/pdf"}),
		NewTable(TableHandle{Blob: "sha256:y", Format: "csv", Columns: []Column{{Name: "a", Type: "int"}}}),
		rec,
		NewError("e", "m"),
	}
	for _, v := range vals {
		b, err := json.Marshal(v)
		if err != nil {
			t.Fatalf("marshal %s: %v", v.Kind, err)
		}
		var got Value
		if err := json.Unmarshal(b, &got); err != nil {
			t.Fatalf("unmarshal %s: %v", v.Kind, err)
		}
		if got.Kind != v.Kind {
			t.Errorf("kind %s round-tripped as %s", v.Kind, got.Kind)
		}
		again, err := json.Marshal(got)
		if err != nil {
			t.Fatal(err)
		}
		if string(again) != string(b) {
			t.Errorf("%s is not stable across a round trip:\n%s\n%s", v.Kind, b, again)
		}
	}
}

// The kernel is a closed set of five (spec §5). A Go runner that skipped an
// unrecognised variant would hand downstream tasks a zero Value and the failure
// would surface far from its cause.
func TestUnknownKindIsRefused(t *testing.T) {
	var v Value
	err := json.Unmarshal([]byte(`{"kind":"quaternion","spin":2}`), &v)
	if err == nil {
		t.Fatal("expected an unknown kind to be refused, got nil error")
	}
	if !strings.Contains(err.Error(), "closed set of five") {
		t.Errorf("error should explain the closed set, got: %v", err)
	}
}

func TestMissingKindIsRefused(t *testing.T) {
	var v Value
	if err := json.Unmarshal([]byte(`{"body":"hi"}`), &v); err == nil {
		t.Fatal("expected a value with no kind discriminator to be refused")
	}
}

// A Value whose Kind and populated arm disagree is a programming mistake that
// must not reach the wire as a half-empty object.
func TestMismatchedArmIsRefused(t *testing.T) {
	if _, err := json.Marshal(Value{Kind: KindText}); err == nil {
		t.Fatal("expected marshalling a text value with no Text payload to fail")
	}
}

func TestUnmarshalDataRefusesNonRecord(t *testing.T) {
	var dst map[string]any
	err := NewText("hi").UnmarshalData(&dst)
	if err == nil {
		t.Fatal("expected UnmarshalData on a text value to fail")
	}
}

// A wire type must round-trip its own zero value. Without this, every envelope
// with an absent ref fails to decode somewhere far from the omission.
func TestZeroTypeRefRoundTrips(t *testing.T) {
	b, err := json.Marshal(TypeRef{})
	if err != nil {
		t.Fatal(err)
	}
	if string(b) != `""` {
		t.Fatalf("zero TypeRef marshals as %s", b)
	}
	var got TypeRef
	if err := json.Unmarshal(b, &got); err != nil {
		t.Fatalf("zero TypeRef does not round-trip: %v", err)
	}
	if !got.IsZero() {
		t.Errorf("round-tripped to %+v", got)
	}
}

// Tolerating "" must not become tolerating garbage.
func TestMalformedTypeRefIsStillRefusedOnTheWire(t *testing.T) {
	for _, bad := range []string{`"Invoice"`, `"Invoice@"`, `"Invoice@0"`, `"@1"`} {
		var got TypeRef
		if err := json.Unmarshal([]byte(bad), &got); err == nil {
			t.Errorf("%s was accepted as a type ref", bad)
		}
	}
}

func TestTypeRefRequiresExplicitVersion(t *testing.T) {
	if _, err := ParseTypeRef("Invoice"); err == nil {
		t.Error("a bare name must not imply version 1: an implied version is a pin that silently moves")
	}
	if _, err := ParseTypeRef("Invoice@0"); err == nil {
		t.Error("version 0 must be refused")
	}
	got, err := ParseTypeRef("report.ReportSpec@3")
	if err != nil {
		t.Fatal(err)
	}
	if got.Name != "report.ReportSpec" || got.Version != 3 {
		t.Errorf("parsed %+v", got)
	}
	if got.String() != "report.ReportSpec@3" {
		t.Errorf("round trip gave %q", got.String())
	}
}

// Taint is carried forward, never dropped. Laundering provenance through an
// aggregation is the exact failure mode recording taint exists to make visible.
func TestDeriveCarriesTaint(t *testing.T) {
	in := Envelope{RunID: "r1", TaskID: "t1", Attempt: 2, CausedBy: 7}
	in = in.WithTaint(Taint{Source: "resource:crm"})

	out := in.Derive(Ref("Out", 1), "producer", BudgetSpent{Ms: 5}, time.Unix(0, 0))

	if len(out.Taint) != 1 || out.Taint[0].Source != "resource:crm" {
		t.Fatalf("taint was dropped across Derive: %+v", out.Taint)
	}
	if out.RunID != "r1" || out.TaskID != "t1" || out.Attempt != 2 || out.CausedBy != 7 {
		t.Errorf("causal fields were not preserved: %+v", out)
	}
	if out.Schema.Name != "Out" || out.Producer != "producer" {
		t.Errorf("output fields not set: %+v", out)
	}
}

// Derive must not alias the input's taint slice, or two sibling tasks deriving
// from one envelope would contaminate each other's provenance.
func TestDeriveDoesNotAliasTaint(t *testing.T) {
	in := Envelope{}.WithTaint(Taint{Source: "a"})
	out := in.Derive(Ref("O", 1), "p", BudgetSpent{}, time.Unix(0, 0))
	out = out.WithTaint(Taint{Source: "b"})
	if len(in.Taint) != 1 {
		t.Errorf("mutating the derived envelope changed the source: %+v", in.Taint)
	}
}

func TestWithTaintDeduplicates(t *testing.T) {
	e := Envelope{}
	for i := 0; i < 100; i++ {
		e = e.WithTaint(Taint{Source: "resource:ledger", Reason: "query"})
	}
	if len(e.Taint) != 1 {
		t.Errorf("expected 1 deduplicated mark, got %d", len(e.Taint))
	}
}
