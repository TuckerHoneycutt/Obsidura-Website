package action_test

import (
	"strings"
	"testing"
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/ptnfake"
)

// Named mutation table for the authoring model.
//
//	mutation                                            | reddens
//	----------------------------------------------------|--------------------------------------
//	validateSpec stops requiring Summary                 | TestSummaryIsRequired
//	validateSpec allows retry without idempotent         | TestRetryRequiresIdempotent
//	Register overwrites a duplicate name                 | TestDuplicateRegistrationPanics
//	Register stops honouring kernel.Valuer               | TestValuerOutputChoosesItsOwnKind
//	Register stops passing kernel.Value inputs through   | TestRawValueInputIsPassedThrough
//	Spec gains a wiring field                            | (see emit's TestEmittedTasksDeclareNoWiring)

type in struct {
	N int `json:"n"`
}

type out struct {
	N int `json:"n"`
}

func spec(name string) action.Spec {
	return action.Spec{
		Name: name, Version: 1,
		Input:   kernel.Ref("test.In", 1),
		Output:  kernel.Ref("test.Out", 1),
		Policy:  action.Policy{Timeout: time.Second},
		Summary: "A test action.",
	}
}

func mustPanic(t *testing.T, want string, fn func()) {
	t.Helper()
	defer func() {
		r := recover()
		if r == nil {
			t.Fatalf("expected a panic mentioning %q, got none", want)
		}
		if msg, ok := r.(string); ok && !strings.Contains(msg, want) {
			t.Errorf("panic %q does not mention %q", msg, want)
		}
	}()
	fn()
}

// Registration happens at init, so a bad declaration should stop the binary
// starting rather than surface on the first invocation in production.
func TestSummaryIsRequired(t *testing.T) {
	r := action.NewRegistry()
	s := spec("test.nosummary")
	s.Summary = ""
	mustPanic(t, "Summary is required", func() {
		action.Register(r, s, func(c *action.Ctx, i in) (out, error) { return out{}, nil })
	})
}

// Retrying a non-idempotent action is how one failure becomes two ledger
// entries.
func TestRetryRequiresIdempotent(t *testing.T) {
	r := action.NewRegistry()
	s := spec("test.retry")
	s.Policy = action.Policy{Timeout: time.Second, Retry: 3, Idempotent: false}
	mustPanic(t, "Idempotent", func() {
		action.Register(r, s, func(c *action.Ctx, i in) (out, error) { return out{}, nil })
	})
}

func TestMissingSchemaRefIsRefused(t *testing.T) {
	r := action.NewRegistry()
	s := spec("test.noinput")
	s.Input = kernel.TypeRef{}
	mustPanic(t, "Input schema ref is required", func() {
		action.Register(r, s, func(c *action.Ctx, i in) (out, error) { return out{}, nil })
	})
}

func TestVerblessResourceIsRefused(t *testing.T) {
	r := action.NewRegistry()
	s := spec("test.noverbs")
	s.Uses = []action.ResourceUse{{Name: "ledger"}}
	mustPanic(t, "declares no verbs", func() {
		action.Register(r, s, func(c *action.Ctx, i in) (out, error) { return out{}, nil })
	})
}

func TestDuplicateRegistrationPanics(t *testing.T) {
	r := action.NewRegistry()
	action.Register(r, spec("test.dup"), func(c *action.Ctx, i in) (out, error) { return out{}, nil })
	mustPanic(t, "already registered", func() {
		action.Register(r, spec("test.dup"), func(c *action.Ctx, i in) (out, error) { return out{}, nil })
	})
}

func TestNamesAreSorted(t *testing.T) {
	r := action.NewRegistry()
	for _, n := range []string{"z.one", "a.two", "m.three"} {
		action.Register(r, spec(n), func(c *action.Ctx, i in) (out, error) { return out{}, nil })
	}
	got := strings.Join(r.Names(), ",")
	// Sorted because the handshake and the emitter are both compared
	// byte-for-byte; map order would make the drift gate flap.
	if got != "a.two,m.three,z.one" {
		t.Errorf("Names() returned %q", got)
	}
}

// tableOut lets an action return a Table as naturally as a struct.
type tableOut struct {
	Handle kernel.TableHandle
}

func (t tableOut) KernelValue() kernel.Value { return kernel.NewTable(t.Handle) }

func TestValuerOutputChoosesItsOwnKind(t *testing.T) {
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	defer p.Close()

	r := action.NewRegistry()
	action.Register(r, spec("test.valuer"), func(c *action.Ctx, i in) (tableOut, error) {
		h, err := c.PutTable([]kernel.Column{{Name: "n", Type: "int"}}, [][]any{{1}}, "jsonl")
		return tableOut{Handle: h}, err
	})

	res := p.Invoke(r, "test.valuer", in{N: 1})
	if res.Err != nil {
		t.Fatal(res.Err)
	}
	if res.Value.Kind != kernel.KindTable {
		t.Fatalf("output kind is %q; a Valuer output must pick its own kernel representation", res.Value.Kind)
	}
	if res.Value.Table.Blob == "" {
		t.Error("no table handle in the output value")
	}
}

// An action that legitimately handles a File or Table input takes the raw
// Value rather than a Record.
func TestRawValueInputIsPassedThrough(t *testing.T) {
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	defer p.Close()

	r := action.NewRegistry()
	action.Register(r, spec("test.rawin"), func(c *action.Ctx, v kernel.Value) (out, error) {
		if v.Kind != kernel.KindText {
			return out{}, nil
		}
		return out{N: len(v.Text.Body)}, nil
	})

	res := p.Invoke(r, "test.rawin", kernel.NewText("abcde"))
	if res.Err != nil {
		t.Fatal(res.Err)
	}
	var got out
	if err := res.Record(&got); err != nil {
		t.Fatal(err)
	}
	if got.N != 5 {
		t.Errorf("the raw Value did not reach the body: got %+v", got)
	}
}

// A wrong-shape payload must be a named error, not a struct of zero fields
// three tasks downstream.
func TestWrongInputSchemaIsRefused(t *testing.T) {
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	defer p.Close()

	r := action.NewRegistry()
	action.Register(r, spec("test.strict"), func(c *action.Ctx, i in) (out, error) {
		return out{N: i.N}, nil
	})

	wrong, err := kernel.NewRecord(kernel.Ref("test.SomethingElse", 1), in{N: 7})
	if err != nil {
		t.Fatal(err)
	}
	res := p.Invoke(r, "test.strict", wrong)
	if res.Err == nil {
		t.Fatal("a payload carrying the wrong schema ref must be refused")
	}
	if !strings.Contains(res.Err.Error(), "declared input") {
		t.Errorf("error should name the mismatch: %v", res.Err)
	}
}

func TestTaintIsRecordedOnResourceAccess(t *testing.T) {
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	defer p.Close()
	p.AddPostgresFunc("ledger", func(sql string, params []any) (*resRows, error) { return nil, nil })

	r := action.NewRegistry()
	s := spec("test.taint")
	s.Uses = []action.ResourceUse{{Name: "ledger", Verbs: []string{"query"}}}
	action.Register(r, s, func(c *action.Ctx, i in) (out, error) {
		c.Taint("resource:ledger", "manual")
		return out{}, nil
	})

	res := p.Invoke(r, "test.taint", in{})
	if res.Err != nil {
		t.Fatal(res.Err)
	}
	// Recorded and logged, never enforced, in v0 (spec §6). Recording it now is
	// what makes enforcing it later a policy change rather than a retrofit of
	// provenance nobody kept.
	if len(res.Envelope.Taint) != 1 || res.Envelope.Taint[0].Source != "resource:ledger" {
		t.Errorf("taint did not reach the outbound envelope: %+v", res.Envelope.Taint)
	}
}
