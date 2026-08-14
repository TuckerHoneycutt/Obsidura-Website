package deck_test

import (
	"sort"
	"strings"
	"testing"

	"github.com/obsidura/pantheon-go/deck"
)

// Named mutation table for the deck surface.
//
//	mutation                                       | reddens
//	-----------------------------------------------|--------------------------------------
//	All() stops registering a vertical              | TestAllRegistersEveryVertical
//	Catalog stops sorting                           | TestCatalogIsSortedAndComplete
//	Catalog invents a summary for a blank one       | TestEveryCardCarriesItsOwnSummary
//	vertical() returns the whole name               | TestCardsCarryTheirVertical
//	Catalog omits Uses                              | TestCardsDeclareTheResourcesTheyNeed

func TestAllRegistersEveryVertical(t *testing.T) {
	names := deck.All().Names()
	counts := map[string]int{}
	for _, n := range names {
		counts[strings.SplitN(n, ".", 2)[0]]++
	}

	// The deck is what a customer buys. A vertical silently dropping out of the
	// binary is the failure this catches, and it would otherwise show up as a
	// missing button nobody noticed.
	for vertical, want := range map[string]int{
		"finance":   5,
		"telemetry": 4,
		"clinical":  3,
	} {
		if counts[vertical] != want {
			t.Errorf("vertical %q registered %d actions, want %d", vertical, counts[vertical], want)
		}
	}
	if len(names) != 12 {
		t.Errorf("registry holds %d actions, want 12", len(names))
	}
}

func TestCatalogIsSortedAndComplete(t *testing.T) {
	reg := deck.All()
	cards := deck.Catalog(reg)

	if len(cards) != len(reg.Names()) {
		t.Fatalf("catalog has %d cards for %d registered actions", len(cards), len(reg.Names()))
	}

	names := make([]string, len(cards))
	for i, c := range cards {
		names[i] = c.Name
	}
	if !sort.StringsAreSorted(names) {
		t.Errorf("catalog is not sorted; the GUI's button order would shuffle between builds:\n%v", names)
	}
}

// Summary is a required field precisely so this holds. An action with no
// summary is an unlabelled button.
func TestEveryCardCarriesItsOwnSummary(t *testing.T) {
	seen := map[string]string{}
	for _, c := range deck.Catalog(deck.All()) {
		if strings.TrimSpace(c.Summary) == "" {
			t.Errorf("action %q has no summary", c.Name)
		}
		if !strings.HasSuffix(c.Summary, ".") {
			t.Errorf("action %q summary should read as a sentence: %q", c.Name, c.Summary)
		}
		if prev, dup := seen[c.Summary]; dup {
			t.Errorf("actions %q and %q share a summary; the deck would show two identical buttons",
				prev, c.Name)
		}
		seen[c.Summary] = c.Name
	}
}

func TestCardsCarryTheirVertical(t *testing.T) {
	for _, c := range deck.Catalog(deck.All()) {
		want := strings.SplitN(c.Name, ".", 2)[0]
		if c.Vertical != want {
			t.Errorf("action %q reports vertical %q, want %q", c.Name, c.Vertical, want)
		}
		if c.Vertical == c.Name {
			t.Errorf("action %q vertical was not split off the name", c.Name)
		}
	}
}

// The catalog tells the GUI which grants a caller needs before pressing the
// button. Dropping that turns a permission error into a mystery.
func TestCardsDeclareTheResourcesTheyNeed(t *testing.T) {
	byName := map[string][]string{}
	for _, c := range deck.Catalog(deck.All()) {
		byName[c.Name] = c.Resources
		if !sort.StringsAreSorted(c.Resources) {
			t.Errorf("action %q resources are not sorted: %v", c.Name, c.Resources)
		}
	}

	if got := byName["finance.match_receipts"]; len(got) != 1 || got[0] != "receipts" {
		t.Errorf("finance.match_receipts needs %v, want [receipts]", got)
	}
	// reconcile_ledger reads only the table handed to it.
	if got := byName["finance.reconcile_ledger"]; len(got) != 0 {
		t.Errorf("finance.reconcile_ledger declares %v; it touches no resource", got)
	}
}

func TestCardsCarryTheirContract(t *testing.T) {
	for _, c := range deck.Catalog(deck.All()) {
		if !strings.Contains(c.Input, "@") || !strings.Contains(c.Output, "@") {
			t.Errorf("action %q has unversioned refs: input=%q output=%q", c.Name, c.Input, c.Output)
		}
		if c.Version < 1 {
			t.Errorf("action %q has version %d", c.Name, c.Version)
		}
	}
}

// The catalog must be derived, not maintained: two calls describe the same
// registry identically.
func TestCatalogIsStable(t *testing.T) {
	a := deck.Catalog(deck.All())
	b := deck.Catalog(deck.All())
	if len(a) != len(b) {
		t.Fatalf("%d vs %d cards", len(a), len(b))
	}
	for i := range a {
		if !sameCard(a[i], b[i]) {
			t.Errorf("card %d differs between calls:\n  %+v\n  %+v", i, a[i], b[i])
		}
	}
}

// sameCard compares two cards field by field. Card holds a slice, so it is not
// comparable with ==.
func sameCard(a, b deck.Card) bool {
	if a.Name != b.Name || a.Version != b.Version || a.Vertical != b.Vertical ||
		a.Summary != b.Summary || a.Input != b.Input || a.Output != b.Output ||
		len(a.Resources) != len(b.Resources) {
		return false
	}
	for i := range a.Resources {
		if a.Resources[i] != b.Resources[i] {
			return false
		}
	}
	return true
}
