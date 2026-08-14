package emit_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/deck"
	"github.com/obsidura/pantheon-go/emit"
	"github.com/obsidura/pantheon-go/kernel"
)

// Named mutation table for the emitter.
//
//	mutation                                        | reddens
//	------------------------------------------------|------------------------------------------
//	Spec gains a Next/Then field and emit writes it  | TestEmittedTasksDeclareNoWiring
//	yamlScalar stops quoting reserved words          | TestReservedWordSummaryIsQuoted
//	Registry.Names stops sorting                     | TestEmitIsByteStableAcrossRuns
//	Check ignores files no action produces           | TestCheckDetectsAnOrphan
//	Check compares nothing                           | TestCheckDetectsAnEdit
//	emit interpolates anything at all                | TestEmittedYAMLContainsNoExpressionSyntax

func TestEmitIsByteStableAcrossRuns(t *testing.T) {
	// The drift gate compares bytes, so map iteration order anywhere in the
	// emitter would make CI flap and then be disabled.
	a, err := emit.Definitions(deck.All())
	if err != nil {
		t.Fatal(err)
	}
	b, err := emit.Definitions(deck.All())
	if err != nil {
		t.Fatal(err)
	}
	if len(a) != len(b) {
		t.Fatalf("emitted %d files then %d", len(a), len(b))
	}
	for i := range a {
		if a[i].Path != b[i].Path {
			t.Fatalf("file %d is %q then %q", i, a[i].Path, b[i].Path)
		}
		if string(a[i].Content) != string(b[i].Content) {
			t.Errorf("%s differs between runs", a[i].Path)
		}
	}
}

// Invariant 3: edges are derived from references, never authored. Go owns what
// an action IS; hand-authored YAML owns how actions are WIRED. If the emitter
// ever writes an edge, the SDK has broken the invariant from the inside.
func TestEmittedTasksDeclareNoWiring(t *testing.T) {
	files, err := emit.Definitions(deck.All())
	if err != nil {
		t.Fatal(err)
	}
	forbidden := []string{"\non:", "\nthen:", "\ndepends_on:", "\nnext:"}
	var checked int
	for _, f := range files {
		if !strings.HasPrefix(f.Path, "tasks/") {
			continue
		}
		checked++
		body := string(f.Content)
		for _, k := range forbidden {
			if strings.Contains(body, k) {
				t.Errorf("%s emits wiring key %q; edges are authored in YAML, not generated from Go",
					f.Path, strings.TrimSpace(k))
			}
		}
	}
	if checked == 0 {
		t.Fatal("no task files were checked; the assertion above was vacuous")
	}
}

// Invariant 2: no expression language, ever. A generated definition must be
// literal data -- if the emitter grew a template, this is where it shows.
func TestEmittedYAMLContainsNoExpressionSyntax(t *testing.T) {
	files, err := emit.Definitions(deck.All())
	if err != nil {
		t.Fatal(err)
	}
	forbidden := []string{"${", "{{", "$(", "!!python", "<%"}
	for _, f := range files {
		if !strings.HasPrefix(f.Path, "tasks/") {
			continue
		}
		for _, k := range forbidden {
			if strings.Contains(string(f.Content), k) {
				t.Errorf("%s contains %q, which is interpolation syntax", f.Path, k)
			}
		}
	}
}

func TestEmittedTaskCarriesTheDeclaredContract(t *testing.T) {
	files, err := emit.Definitions(deck.All())
	if err != nil {
		t.Fatal(err)
	}
	var body string
	for _, f := range files {
		if f.Path == filepath.Join("tasks", "finance", "match_receipts.yaml") {
			body = string(f.Content)
		}
	}
	if body == "" {
		t.Fatal("finance/match_receipts.yaml was not emitted")
	}

	for _, want := range []string{
		"kind: task",
		"name: finance.match_receipts",
		"runtime: go",
		"input: finance.ReceiptMatchRequest@1",
		"output: finance.ReceiptMatchReport@1",
		"- name: receipts",
		"verbs: [get, list]",
		"idempotent: true",
	} {
		if !strings.Contains(body, want) {
			t.Errorf("emitted task is missing %q:\n%s", want, body)
		}
	}
}

// YAML 1.1 readers coerce these to booleans. A summary of "no" becoming false
// is the kind of bug that survives review.
func TestReservedWordSummaryIsQuoted(t *testing.T) {
	r := action.NewRegistry()
	action.Register(r, action.Spec{
		Name: "test.reserved", Version: 1,
		Input:   kernel.Ref("test.In", 1),
		Output:  kernel.Ref("test.Out", 1),
		Policy:  action.Policy{Timeout: time.Second},
		Summary: "no",
	}, func(c *action.Ctx, in struct{}) (struct{}, error) { return struct{}{}, nil })

	files, err := emit.Definitions(r)
	if err != nil {
		t.Fatal(err)
	}
	for _, f := range files {
		if strings.HasSuffix(f.Path, "reserved.yaml") {
			if !strings.Contains(string(f.Content), `summary: "no"`) {
				t.Errorf("a reserved word must be quoted:\n%s", f.Content)
			}
			return
		}
	}
	t.Fatal("test task was not emitted")
}

func TestCheckPassesOnFreshlyWrittenFiles(t *testing.T) {
	dir := t.TempDir()
	files, err := emit.Definitions(deck.All())
	if err != nil {
		t.Fatal(err)
	}
	if err := emit.Write(dir, files); err != nil {
		t.Fatal(err)
	}
	drifted, err := emit.Check(dir, files)
	if err != nil {
		t.Fatal(err)
	}
	if len(drifted) != 0 {
		t.Errorf("freshly written definitions reported as drifted: %v", drifted)
	}
}

func TestCheckDetectsAnEdit(t *testing.T) {
	dir := t.TempDir()
	files, _ := emit.Definitions(deck.All())
	if err := emit.Write(dir, files); err != nil {
		t.Fatal(err)
	}

	target := filepath.Join(dir, "tasks", "finance", "reconcile_ledger.yaml")
	body, err := os.ReadFile(target)
	if err != nil {
		t.Fatal(err)
	}
	edited := strings.Replace(string(body), "retry: 2", "retry: 99", 1)
	if edited == string(body) {
		t.Fatal("test could not edit the file; the assertion below would be vacuous")
	}
	if err := os.WriteFile(target, []byte(edited), 0o644); err != nil {
		t.Fatal(err)
	}

	drifted, err := emit.Check(dir, files)
	if err != nil {
		t.Fatal(err)
	}
	if len(drifted) != 1 || !strings.Contains(drifted[0], "reconcile_ledger") {
		t.Errorf("a hand edit must be caught; drift report was %v", drifted)
	}
}

// An orphan is worse than a missing file: ptn apply would happily register a
// definition for an action that no longer exists.
func TestCheckDetectsAnOrphan(t *testing.T) {
	dir := t.TempDir()
	files, _ := emit.Definitions(deck.All())
	if err := emit.Write(dir, files); err != nil {
		t.Fatal(err)
	}
	orphan := filepath.Join(dir, "tasks", "finance", "deleted_action.yaml")
	if err := os.WriteFile(orphan, []byte("kind: task\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	drifted, err := emit.Check(dir, files)
	if err != nil {
		t.Fatal(err)
	}
	var found bool
	for _, d := range drifted {
		if strings.Contains(d, "orphan") {
			found = true
		}
	}
	if !found {
		t.Errorf("a definition no action produces must be reported; got %v", drifted)
	}
}

func TestCheckDetectsAMissingFile(t *testing.T) {
	dir := t.TempDir()
	files, _ := emit.Definitions(deck.All())
	if err := emit.Write(dir, files); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(filepath.Join(dir, "tasks", "clinical", "filter_cohort.yaml")); err != nil {
		t.Fatal(err)
	}
	drifted, err := emit.Check(dir, files)
	if err != nil {
		t.Fatal(err)
	}
	if len(drifted) != 1 || !strings.Contains(drifted[0], "missing") {
		t.Errorf("a deleted definition must be caught; got %v", drifted)
	}
}

// The committed definitions/ directory is the artifact of record. This is the
// gate that keeps it honest, run as an ordinary test so it cannot be skipped.
func TestCommittedDefinitionsAreInSync(t *testing.T) {
	root := filepath.Join("..", "definitions")
	if _, err := os.Stat(root); os.IsNotExist(err) {
		t.Skip("definitions/ has not been generated yet; run `ptn-gen emit`")
	}
	files, err := emit.Definitions(deck.All())
	if err != nil {
		t.Fatal(err)
	}
	drifted, err := emit.Check(root, files)
	if err != nil {
		t.Fatal(err)
	}
	if len(drifted) > 0 {
		t.Errorf("definitions/ has drifted from the registry; run `go run ./cmd/ptn-gen emit` and commit:\n  %s",
			strings.Join(drifted, "\n  "))
	}
}
